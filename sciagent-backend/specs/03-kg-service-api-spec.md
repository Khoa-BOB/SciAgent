# KG Service — API Specification

Phase 2 of the backend SDLC (see [`00-overview.md`](00-overview.md)). This is
the concrete REST contract; see [`02-kg-service-architecture.md`](02-kg-service-architecture.md)
for conventions (versioning, error shape, list-response shape) that apply to
every endpoint below without being repeated per-endpoint.

Base path: `/v1`. All endpoints require `X-Service-Key` unless marked public.
§8's `/v1/ingest-jobs` endpoints require a **separate, write-scoped**
`X-Service-Key` (checked against `KG_SERVICE_WRITE_ALLOWED_KEYS`, not the
`KG_SERVICE_ALLOWED_KEYS` every other endpoint below uses) — see architecture
doc §8.2.

---

## 1. Health

### `GET /healthz`

Process liveness only — never touches Neo4j. Returns `200` if the process is
running.

```json
{"status": "ok"}
```

### `GET /readyz`

Readiness — runs a trivial Neo4j query (`RETURN 1`) via the shared driver.
`503` if Neo4j is unreachable.

```json
{"status": "ok", "neo4j": "reachable"}
```

Both are unauthenticated (public) — load balancers and orchestrators need to
call these without a service key.

---

## 2. Papers

### `GET /v1/papers/{arxiv_id}`

Wraps `PaperSearch.get_by_id` (`src/retrieval/search.py`).

**Response `200`**
```json
{
  "paper_id": "0704.0001",
  "title": "Calculation of prompt diphoton production cross sections...",
  "abstract": "A fully differential calculation...",
  "authors": ["C. Balázs", "E. L. Berger", "P. M. Nadolsky", "C.-P. Yuan"],
  "categories": ["hep-ph"],
  "journal": "Phys.Rev.D76:013009,2007",
  "doi": "10.1103/PhysRevD.76.013009",
  "update_date": "2008-11-26",
  "versions": ["v1", "v2"]
}
```
Note: `embedding` is deliberately excluded from this response (large, not
useful to a caller rendering a page) — see §7 for the one endpoint that needs
it internally.

**Errors**: `404 PAPER_NOT_FOUND`.

### `GET /v1/papers/{arxiv_id}/entities`

Domain entities extracted for this paper (`USES_METHOD`/`USES_DATASET`/
`STUDIES_TOPIC`, `sciagent-KG/queries/entities.py`).

**Response `200`**
```json
{
  "paper_id": "2401.12345",
  "methods": [{"name": "Graph Attention Network", "confidence": 0.9}],
  "datasets": [{"name": "ogbn-arxiv", "confidence": 0.85}],
  "topics": [{"name": "molecular property prediction", "confidence": 0.8}]
}
```
Empty arrays (not `404`) if the paper exists but extraction found nothing —
matches the pipeline's own semantics (`entities: []` is a valid outcome, see
`sciagent-KG` extraction pipeline notes on empty-entity records).

**Errors**: `404 PAPER_NOT_FOUND` if the paper itself doesn't exist.

---

## 3. Search

### `GET /v1/search/fulltext`

Wraps `PaperSearch.search_fulltext` (Neo4j `paper_text` full-text index).

| Param | Type | Required | Default | Cap |
|---|---|---|---|---|
| `q` | string | yes | — | — |
| `limit` | int | no | 10 | 100 |

**Response `200`**
```json
{
  "items": [
    {"paper_id": "2401.12345", "title": "...", "abstract": "...", "score": 4.82}
  ],
  "count": 1
}
```

**Errors**: `400 EMPTY_QUERY` if `q` is blank.

### `GET /v1/search/semantic`

Wraps `PaperVectorSearch.search` (`src/retrieval/vector_search.py`) — embeds
`q` server-side with `google/embeddinggemma-300m`, queries the
`paper_embedding_index` vector index.

| Param | Type | Required | Default | Cap |
|---|---|---|---|---|
| `q` | string | yes | — | — |
| `top_k` | int | no | 5 | 50 |

**Response `200`**
```json
{
  "items": [
    {"paper_id": "2401.12345", "title": "...", "abstract": "...", "score": 0.812}
  ],
  "count": 1
}
```

**Errors**: `400 EMPTY_QUERY`.

### `POST /v1/search/semantic/by-embedding`

Advanced path for `PaperVectorSearch.search_by_embedding` — caller supplies
an already-computed embedding (must match the service's model dimensionality;
mismatches are rejected, not silently truncated/padded).

**Request**
```json
{"embedding": [0.0123, -0.0456, ...], "top_k": 5}
```

**Response**: same shape as `/v1/search/semantic`.

**Errors**: `422 INVALID_EMBEDDING_DIMENSION`.

### `GET /v1/search/by-author`

Wraps `PaperSearch.search_by_author` — substring match on normalized name.

| Param | Type | Required | Default | Cap |
|---|---|---|---|---|
| `name` | string | yes | — | — |
| `limit` | int | no | 10 | 100 |

**Response `200`**: same list shape, each item includes `matched_by` (the
matched author's display name).

### `GET /v1/search/by-category`

Wraps `PaperSearch.search_by_category` — exact category code (e.g. `cs.AI`).

| Param | Type | Required | Default | Cap |
|---|---|---|---|---|
| `code` | string | yes | — | — |
| `limit` | int | no | 10 | 100 |

**Errors**: `404 CATEGORY_NOT_FOUND` if the code doesn't exist in the graph
(distinguishes "valid code, zero results" — not applicable here since a
nonexistent category always has zero papers — from "typo'd code"; see Testing
doc for how this is verified against the real category list).

### `GET /v1/search/by-year`

Wraps `PaperSearch.search_by_year` — inclusive range.

| Param | Type | Required | Default | Cap |
|---|---|---|---|---|
| `start_year` | int | yes | — | — |
| `end_year` | int | no | `start_year` | — |
| `limit` | int | no | 10 | 100 |

**Errors**: `400 INVALID_YEAR_RANGE` if `end_year < start_year`.

---

## 4. Graph expansion

### `POST /v1/graph/expand`

Wraps `GraphExpander.expand` (`src/retrieval/graph_expand.py`) exactly —
seed context (authors/categories/journal per seed) plus a ranked, deduped
related-paper list, optionally weighted by similarity to a query embedding.

**Request**
```json
{
  "paper_ids": ["2401.12345", "2401.67890"],
  "query_embedding": null,
  "related_limit": 5,
  "pool_size": 20
}
```
`query_embedding` is optional — omit it to rank purely by shared-author/
shared-category weighting (matches `GraphExpander.expand`'s `None` path).
`related_limit` capped at 50, `pool_size` capped at 200 server-side
regardless of the request body.

**Response `200`**
```json
{
  "seed_context": {
    "2401.12345": {
      "authors": ["Jane Doe"],
      "categories": ["cs.AI"],
      "journal": null
    }
  },
  "related_papers": [
    {
      "paper_id": "2312.00001",
      "title": "...",
      "shared_authors": ["Jane Doe"],
      "shared_categories": [],
      "similarity_to_query": 0.0
    }
  ]
}
```

**Errors**: `400 EMPTY_PAPER_IDS` if `paper_ids` is empty (matches
`GraphExpander.expand`'s own early-return, made explicit as a client error
instead of a silent empty success).

---

## 5. Domain entities

### `GET /v1/entities/{entity_type}`

Browse/search known entities of a given type by name substring.

Path param `entity_type` ∈ `{method, dataset, topic}` — anything else is
`400 UNKNOWN_ENTITY_TYPE` (validated against the same fixed dict as
`sciagent-KG/queries/entities.py:ENTITY_LABELS`, never string-built into
Cypher from the path param directly).

| Query param | Type | Required | Default | Cap |
|---|---|---|---|---|
| `q` | string | no | — (lists all if omitted) | — |
| `limit` | int | no | 20 | 200 |

**Response `200`**
```json
{"items": [{"name": "Graph Attention Network", "normalized_name": "graph attention network"}], "count": 1}
```

### `GET /v1/entities/{entity_type}/{normalized_name}/papers`

Papers using a given entity (reverse of §2's per-paper entity list).

| Param | Type | Required | Default | Cap |
|---|---|---|---|---|
| `limit` | int | no | 20 | 200 |

**Response `200`**
```json
{
  "items": [
    {"paper_id": "2401.12345", "title": "...", "confidence": 0.9}
  ],
  "count": 1
}
```

**Errors**: `400 UNKNOWN_ENTITY_TYPE`; `404 ENTITY_NOT_FOUND` if the
`normalized_name` doesn't exist for that type.

---

## 6. Stats

### `GET /v1/stats`

Corpus-level counts — cheap `count(*)` queries, useful after an
ingestion/extraction run and for dashboards.

**Response `200`**
```json
{
  "paper_count": 36009,
  "author_count": 128441,
  "category_count": 176,
  "entity_counts": {"method": 4213, "dataset": 1876, "topic": 5502},
  "papers_with_entities": 35981
}
```

---

## 7. Internal-only: raw embedding lookup

### `GET /v1/papers/{arxiv_id}/embedding`

Returns the paper's stored embedding vector. Separate from
`GET /v1/papers/{arxiv_id}` deliberately (§2) — only the Retrieval/MCP
Service's reranking step needs this, and it's large enough not to want it in
every paper-lookup response by default.

**Response `200`**
```json
{"paper_id": "2401.12345", "embedding": [0.0123, -0.0456, ...]}
```

**Errors**: `404 PAPER_NOT_FOUND`, `404 EMBEDDING_NOT_AVAILABLE` if the paper
exists but has no stored embedding (e.g. ingested before the embedding index
was built).

---

## 8. Ingestion (write path)

Everything above this section is read-only. These two endpoints are the
exception — gated by the separate, write-scoped key described at the top of
this document. A key valid for every read endpoint above is not
automatically valid here. See architecture doc §8 for the full design
(job queue, credential boundary, upload validation).

### `POST /v1/ingest-jobs`

Upload a JSONL file of new/updated arXiv-style paper metadata — same shape
`sciagent-KG/src/ingestion/transform.py` already expects (each line a JSON
object with at least a non-empty `id` field). Validated synchronously; the
actual ingestion (`schema → load → embed → validate`) runs asynchronously on
a worker.

**Request**: `multipart/form-data`, field `file`.

**Response `202`**
```json
{"job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6", "status": "queued", "record_count": 128}
```

**Errors**:
- `413 INGEST_FILE_TOO_LARGE` — exceeds `MAX_INGEST_FILE_BYTES` (default 200MB).
- `422 INGEST_FILE_EMPTY` — file has no non-blank lines.
- `422 INGEST_FILE_INVALID_JSONL` — a line isn't valid JSON, isn't an object,
  or is missing a non-empty `id` field.
- `503 INGEST_STORAGE_UNAVAILABLE` — MinIO unreachable.
- `503 INGEST_QUEUE_UNAVAILABLE` — Redis unreachable.

### `GET /v1/ingest-jobs/{job_id}`

Poll job status. `status` is one of RQ's job states (`queued`, `started`,
`finished`, `failed`, ...).

**Response `200`** (queued/running)
```json
{"job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6", "status": "started", "result": null, "error": null}
```

**Response `200`** (finished)
```json
{
  "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "status": "finished",
  "result": {
    "loaded": 128,
    "embedded": 128,
    "validation_passed": true,
    "validation_violations": {}
  },
  "error": null
}
```

**Response `200`** (failed)
```json
{"job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6", "status": "failed", "result": null, "error": "Traceback (most recent call last): ..."}
```

**Errors**: `404 INGEST_JOB_NOT_FOUND`.

Note: entity extraction (Method/Dataset/ResearchTopic) is not triggered by
this endpoint — see architecture doc §8.4.

---

## 9. Endpoint summary

```text
GET  /healthz
GET  /readyz
GET  /v1/papers/{arxiv_id}
GET  /v1/papers/{arxiv_id}/entities
GET  /v1/papers/{arxiv_id}/embedding
GET  /v1/search/fulltext
GET  /v1/search/semantic
POST /v1/search/semantic/by-embedding
GET  /v1/search/by-author
GET  /v1/search/by-category
GET  /v1/search/by-year
POST /v1/graph/expand
GET  /v1/entities/{entity_type}
GET  /v1/entities/{entity_type}/{normalized_name}/papers
GET  /v1/stats
POST /v1/ingest-jobs                 -- write-scoped key, see §8
GET  /v1/ingest-jobs/{job_id}        -- write-scoped key, see §8
```

Every read endpoint above maps to an existing class/query in `sciagent-KG`
(§9 of the architecture doc lists the two small additive exceptions: entity
reverse-lookup queries and the stats query). The two ingestion endpoints map
to `sciagent-KG`'s existing ingestion CLI functions, orchestrated rather than
reimplemented (architecture doc §8.1).
