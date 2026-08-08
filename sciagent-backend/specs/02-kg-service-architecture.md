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

## 8. What changes in `sciagent-KG` to support this

Minimal, additive only:

- New **read-side** entity-lookup query templates in `queries/entities.py`
  (papers-by-entity, entities-for-paper) alongside the existing
  upsert/relate templates — same "type string looked up from a fixed dict"
  safety pattern already used there, not user input concatenated into
  Cypher.
- A `stats` query (paper count, entity counts by label) — trivial `MATCH ...
  RETURN count(*)` queries, net new but tiny.
- No changes to ingestion, extraction, or the graph schema itself.

## 9. Exit criteria for this phase

- Every endpoint in [`03-kg-service-api-spec.md`](03-kg-service-api-spec.md)
  maps to exactly one existing (or explicitly-flagged-new) query/class in
  `sciagent-KG`.
- Read vs. write separation is unambiguous: this service holds only
  read-only Neo4j credentials, enforced at the database user level, not just
  by convention in application code.
- The error model and versioning scheme are fixed before implementation
  starts — changing them later is a breaking change for every caller.
