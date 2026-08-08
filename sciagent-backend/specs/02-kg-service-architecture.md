# KG Service — Architecture and Technical Design

Phase 2 of the backend SDLC (see [`00-overview.md`](00-overview.md)).

## 1. Service boundary

```text
                        Internal callers
       (Retrieval/MCP Service, Agent, BFF, eval tooling)
                              |
                              | HTTPS + service-to-service API key
                              v
                    +---------------------+
                    |     KG Service      |
                    |  (FastAPI, stateless)|
                    +---------------------+
                              |
             imports as a library (same process)
                              |
                              v
        sciagent-KG: queries/*.py, src/retrieval/*.py, src/config.py
                              |
                              v
                    Neo4j (read-only credentials)
```

The KG Service does **not** re-implement Cypher. It is a thin FastAPI layer
over the existing, already-tested Python classes:

- `queries.search.PaperSearch` equivalent → `src/retrieval/search.py`
  (`PaperSearch`)
- `src/retrieval/vector_search.py` (`PaperVectorSearch`)
- `src/retrieval/graph_expand.py` (`GraphExpander`)
- `queries/entities.py` (entity upsert/lookup query templates — read-side
  lookups added alongside these for the API, following the same
  parameterized-by-fixed-dict pattern so entity type strings from callers
  never get string-built into Cypher)

This means `sciagent-backend` depends on `sciagent-KG` as a path/library
dependency (same `uv` workspace, or `sciagent-KG` installed editable) rather
than duplicating query logic. A bug fixed in `sciagent-KG`'s query layer is
fixed for the API automatically.

## 2. Why FastAPI

- Matches the existing stack: `sciagent-KG` is already Python + `uv`,
  already depends on the `neo4j` driver and `sentence-transformers` directly
  — no second language/runtime to operate.
  automatic OpenAPI schema generation.
- Pydantic response models map directly onto the existing dataclasses
  (`PaperSummary`, `PaperDetails`, `SearchResult`, `RelatedPaper`,
  `ExpandedResult`) — mostly a `@dataclass` → `BaseModel` translation, not a
  redesign.
- Async endpoints let a single worker handle concurrent Neo4j calls (the
  `neo4j` driver's session/connection pooling does the actual concurrency
  work; FastAPI just doesn't block on it).

## 3. Process and connection model

- One Neo4j `Driver` per process, created at startup (`GraphDatabase.driver`,
  reusing `src/config.py:get_driver`), shared across requests — never one
  driver per request. The driver already pools connections internally.
- All KG Service Cypher calls use `routing_="r"` (read replica routing where
  available) — every existing query in `src/retrieval/*.py` already does
  this; the API layer must not lose it when wrapping them.
- Neo4j credentials for this service are a **separate, read-only** user from
  the one `sciagent-KG`'s ingestion/extraction CLIs use. See
  [`04-kg-service-nfr-testing-deployment.md`](04-kg-service-nfr-testing-deployment.md) §Security.
- The service is stateless: no in-process caching of per-request state, so
  it can run as multiple replicas behind a load balancer immediately. An
  optional shared cache (e.g. Redis) for hot paper lookups is a Phase 6
  (Operation) optimization, not a v1 requirement — see §7.

## 4. Request/response conventions

- All endpoints are versioned under `/v1/`. A breaking change to a response
  shape ships as `/v2/...`, not a mutation of `/v1/...` — callers (agent,
  BFF) pin a version explicitly.
- JSON in, JSON out. No form-encoded bodies.
- List endpoints return `{"items": [...], "count": <int>}`, never a bare
  array — leaves room to add pagination metadata later without a breaking
  change.
- `limit` parameters are always optional with a documented default and a
  server-enforced maximum (see API spec per-endpoint) — a caller cannot
  request an unbounded result set no matter what value it passes.

## 5. Error model

Structured JSON errors, consistent shape across every endpoint:

```json
{
  "error": {
    "code": "PAPER_NOT_FOUND",
    "message": "No paper with arxiv_id '9999.99999'.",
    "details": {}
  }
}
```

| HTTP status | Meaning | Example |
|---|---|---|
| 400 | Malformed/invalid request | empty search query, unknown entity type |
| 404 | Resource not found | unknown `arxiv_id` |
| 422 | Valid JSON, fails schema validation | `top_k` not an integer |
| 429 | Caller exceeded its rate limit | too many requests from one service key |
| 500 | Unhandled server error | — logged with a request ID, never leaks a stack trace to the caller |
| 503 | Neo4j unavailable | `/readyz` and any endpoint failing to reach Neo4j |

Error codes are a fixed, documented enum (grows over time, never reused for
a different meaning) so callers can branch on `error.code` instead of
parsing `error.message`.

## 6. Authentication (service-to-service)

No end-user auth here (BFF's job — see §5 of
[`01-kg-service-requirements.md`](01-kg-service-requirements.md)). Callers
authenticate with a static API key in an `X-Service-Key` header, checked
against a small allowlist of known internal services. This is intentionally
simple for v1 — mTLS or a proper service-mesh identity is a Phase 6 hardening
step once there's more than one deployment environment to justify it.

## 7. Caching strategy (deferred, documented so it isn't accidentally designed against)

Not built in v1. When it is:

- Paper-by-ID lookups are the best caching candidate (immutable once
  ingested, high read/write ratio).
- Search and graph-expansion results are not cached in v1 — they're
  parameterized enough (arbitrary query text, arbitrary seed sets) that a
  naive cache would have a low hit rate for the added complexity.
- Any future cache sits in front of the service (e.g. an HTTP cache or
  Redis keyed by request), not inside the Neo4j query layer — keeps
  `sciagent-KG`'s query modules cache-agnostic.

## 8. Write path: `/v1/ingest-jobs` (ingestion control plane)

Everything above this section describes the read-only KG Service. `/v1/ingest-jobs`
is the one exception: an authenticated, asynchronous way to add new papers to
the graph without shelling into `sciagent-KG`'s CLI by hand. It answers Story
1.8 in [`01-kg-service-requirements.md`](01-kg-service-requirements.md), and it
does not weaken the read/write boundary in §3 — it adds a second, narrower one.

### 8.1 Why a job queue, not a synchronous write

Ingestion (`schema → load → embed → validate`) already takes real time at
corpus scale (embedding is the dominant cost). A `POST` that ran this inline
would either time out or hold an HTTP connection open for minutes — neither
is acceptable for a request/response API. So the write path is asynchronous:

```text
Caller           KG Service (API)        MinIO         Redis/RQ        Worker process
  |                     |                    |              |                |
  |--POST /v1/ingest-jobs (multipart)------->|              |                |
  |                     |--validate JSONL    |              |                |
  |                     |--put_object------->|              |                |
  |                     |--enqueue(run_ingest_job)---------->|                |
  |<--202 {job_id, status}--------------------|              |                |
  |                     |                    |              |--dequeue------>|
  |                     |                    |<--fget_object-----------------|
  |                     |                    |              |   apply_schema |
  |                     |                    |              |   load_metadata|
  |                     |                    |              |   run_embedding|
  |                     |                    |              |   run_validation
  |--GET /v1/ingest-jobs/{id}--------------------------------Job.fetch(id)-->|
  |<--{status, result}--|                    |              |                |
```

- **MinIO** stages the uploaded file so the API process (validates and
  responds immediately) and the worker process (actually reads and loads it)
  don't need to share a filesystem — same reasoning as every stage boundary
  in `sciagent-KG` already being a file on disk, not an in-memory hand-off
  (see `sciagent-KG/specs/02-architecture.md` §2).
- **Redis/RQ** is the job queue. The API process only ever calls
  `Queue.enqueue()`; it never imports or runs the ingestion pipeline itself.
- The **worker** (`kg_service/worker.py`, run with
  `uv run python -m kg_service.worker`) is a separate process/container from
  `kg_service.main:app`. It runs `kg_service/jobs.py:run_ingest_job`, which
  calls `sciagent-KG`'s own `apply_schema` / `load_metadata` / `run_embedding`
  / `run_validation` functions directly — the same idempotent, resumable
  stages the CLI already runs, not a reimplementation (see
  `sciagent-KG/specs/02-architecture.md` §2–3 for why those stages are
  idempotent/resumable to begin with).

### 8.2 Credential boundary: a second, narrower write path

§3 established that this service's API process holds only read-only Neo4j
credentials. The ingest worker is the one place in `sciagent-backend` that
needs write access, and it is kept separate on purpose:

- The worker builds its own Neo4j driver from `KG_WRITE_NEO4J_URI` /
  `KG_WRITE_NEO4J_USERNAME` / `KG_WRITE_NEO4J_PASSWORD`
  (`kg_service/jobs.py:_write_driver`) — env vars that `kg_service.config`
  and `kg_service.deps` (the API process's modules) never read.
- In deployment, only the worker container's environment is given those
  values (`sciagent-backend/.env.worker.example`); the API container's is
  not. The boundary is enforced by which *process* holds the secret — the
  same mechanism that already separates `sciagent-KG`'s write credential
  from this service's read-only one (§3), not application-code discipline
  alone.
- `/v1/ingest-jobs` is gated by a **separate, smaller** service-key
  allowlist (`KG_SERVICE_WRITE_ALLOWED_KEYS`, checked by
  `require_write_service_key` in `kg_service/auth.py`) than every read
  endpoint's `KG_SERVICE_ALLOWED_KEYS` — a caller authorized to search papers
  is not automatically authorized to add them.

### 8.3 What the API process validates before anything is queued

`kg_service/services/ingest.py` rejects a bad upload before it ever reaches
MinIO or the worker, so a malformed file fails in the request that submitted
it, not several minutes later inside a worker log nobody's watching:

- File size over `MAX_INGEST_FILE_BYTES` (default 200MB) → `413`.
- Not valid UTF-8, not JSONL, or any line missing the `id` field
  `src.ingestion.transform.transform()` requires → `422
  INGEST_FILE_INVALID_JSONL`.
- Zero valid records → `422 INGEST_FILE_EMPTY`.

### 8.4 Entity extraction is opt-in, never automatic

`/v1/ingest-jobs` always runs the ingestion pipeline (metadata + embeddings).
It only runs entity extraction if the caller explicitly passes
`run_extraction=true` — matches the existing non-goal in
`sciagent-KG/specs/01-requirements.md` §4 ("no automatic, unattended
re-extraction on a schedule"). There is no default-on path and no
scheduling; the flag has to be set on every request that wants it, same as
`sciagent-KG`'s own extraction CLI has to be invoked deliberately. Without
the flag, `papers_needing_extraction()` still picks up the new papers
whenever someone runs the extraction CLI separately — this flag is a
convenience for doing it in the same request, not the only way to do it.

### 8.5 The extraction follow-up, when requested

When `run_extraction=true`, the worker (`kg_service/jobs.py:_run_extraction_followup`)
runs the same `export → extract → resolve → merge` stages `sciagent-KG`'s
CLI runs, scoped to exactly the papers this job loaded:

1. **Export**: built directly from the already-downloaded upload (no second
   Neo4j round trip), filtered to papers with a non-blank title/abstract —
   same eligibility rule as `sciagent-KG`'s `export_papers()`.
2. **Extract**: one `ExtractionClient` call per paper (`src.extraction.extract.run_extraction`,
   `resume=False` — a fresh per-job shard has no prior checkpoint to resume).
   Backend configured via `EXTRACTION_BASE_URL`/`EXTRACTION_MODEL`/`EXTRACTION_API_KEY`
   (worker-only env vars, same pattern as `KG_WRITE_NEO4J_*` — never read by
   the API process). Defaults to local Ollama, matching `sciagent-KG`'s own
   CLI default; pointing this at OpenAI costs real money per paper.
3. **Resolve — against the full corpus, not just this job's shard**: `resolve()`
   runs over `sciagent-KG`'s entire persistent `data/extraction/shards/`
   directory (every historical `*.extracted.jsonl`, plus this job's new
   one), not just the papers this job added. Resolving only the new shard
   would compare new mentions against nothing but each other — a paper
   mentioning "CNN" would never get a chance to cluster into the
   already-existing "convolutional neural network" entity, silently minting
   a duplicate every time. Full-corpus resolve also benefits from the
   acronym fallback added in `sciagent-KG/src/extraction/resolve.py` (§9),
   which specifically targets this class of miss. The cost: a full resolve
   is ~15 minutes at current ~160k-unique-name corpus scale and grows with
   the corpus — acceptable for an already-asynchronous job with a long
   timeout, but a real latency/cost tradeoff to know about before enabling
   `run_extraction` on high-frequency ingestion.
4. **Merge — only this job's rows**: `resolve()`'s output spans the whole
   corpus, but `_run_extraction_followup` filters it down to rows whose
   `paper_id` is one of this job's papers before calling `merge_resolved()`.
   `merge` is idempotent either way, but writing back the entire corpus's
   relationships on every single ingest job would be wasteful at scale for
   no benefit — every other paper's relationships are already correct in
   Neo4j from when they were originally merged.

Failure handling: an extraction failure (LLM backend unreachable, etc.) is
caught and reported in the job result's `extraction.error` field, not
raised — ingestion has already committed successfully by the time
extraction runs, so a downstream LLM hiccup must not retroactively turn a
successful "papers added" job into a reported failure.

## 9. What changes in `sciagent-KG` to support this

Minimal, additive only:

- New **read-side** entity-lookup query templates in `queries/entities.py`
  (papers-by-entity, entities-for-paper) alongside the existing
  upsert/relate templates — same "type string looked up from a fixed dict"
  safety pattern already used there, not user input concatenated into
  Cypher.
- A `stats` query (paper count, entity counts by label) — trivial `MATCH ...
  RETURN count(*)` queries, net new but tiny.
- No changes to ingestion or the graph schema itself — §8's worker calls the
  existing `src/ingestion/` functions as-is.
- One change to extraction: an acronym-detection fallback in
  `src/extraction/resolve.py`'s `cluster_names()`, additive alongside the
  existing cosine-similarity check (never replacing it) — see
  `sciagent-KG/specs/04-roadmap.md` Near-term #4 and
  `docs/entity_extraction_pipeline.md` Known Limitations for why this exists
  and what it does/doesn't fix. §8.5's full-corpus resolve directly benefits
  from this, since it's the mechanism most likely to catch a new paper's
  acronym matching an existing expansion (or vice versa).

## 10. Exit criteria for this phase

- Every endpoint in [`03-kg-service-api-spec.md`](03-kg-service-api-spec.md)
  maps to exactly one existing (or explicitly-flagged-new) query/class in
  `sciagent-KG`.
- Read vs. write separation is unambiguous: the API process holds only
  read-only Neo4j credentials, enforced at the database user level, not just
  by convention in application code; the ingest worker's separate write
  credential is scoped to its own process/container only (§8.2).
- The error model and versioning scheme are fixed before implementation
  starts — changing them later is a breaking change for every caller.
- The write path's own credential and key boundaries (§8.2) are verified by
  a test, not just asserted in prose — mirrors the existing read-only
  credential test in `04-kg-service-nfr-testing-deployment.md` §5.
