# KG Service — Non-Functional Requirements, Testing, Deployment

Phases 2 (design), 4 (verification), and 5 (deployment) of the backend SDLC
(see [`00-overview.md`](00-overview.md)).

## 1. Performance targets

| Endpoint class | p95 target | Basis |
|---|---:|---|
| `GET /v1/papers/{id}` | < 100ms | Single indexed `MATCH` (`paper_arxiv_id` uniqueness constraint already exists — `sciagent-KG/docs/graph_schema.md` §7) |
| Full-text search | < 300ms | Neo4j full-text index, already used in production by `search_fulltext` |
| Semantic search | < 500ms | Includes server-side query embedding (`SentenceTransformer.encode`, CPU-bound) + vector index query — embedding the query dominates the latency budget, not the index lookup |
| Graph expansion | < 800ms | Two graph traversals (`RELATED_BY_AUTHOR`, `RELATED_BY_CATEGORY`) each bounded by `pool_size`, plus in-process ranking |
| `/v1/stats` | < 200ms | Aggregate counts; consider a cached/materialized value if corpus growth makes `count(*)` slow (not needed at current ~36k-paper scale) |
| `/healthz` | < 10ms | No I/O |
| `/readyz` | < 50ms | One trivial Neo4j round-trip |
| `POST /v1/ingest-jobs` | < 500ms | Validation (in-memory JSONL scan) + one MinIO `put_object` + one Redis `enqueue` — the target covers only this synchronous part; the ingestion job itself runs on the worker and has no request-latency target (see §6.1) |
| `GET /v1/ingest-jobs/{id}` | < 50ms | One Redis `Job.fetch` |

Targets are p95 under the load profile in §5. Re-baseline after the corpus
materially grows past current scale (~36k papers, ~4-5k domain entities).

## 2. Scalability

- Stateless service — horizontal scaling is just adding replicas behind a
  load balancer, no session affinity required.
- Neo4j connection pooling is per-process (one driver, internal pool) — size
  the pool relative to expected concurrent requests per replica, not per
  request.
- All list/search endpoints have a server-enforced `limit` cap (see API spec)
  — no endpoint can be made to return an unbounded result set regardless of
  what a caller requests.
- Graph expansion's `pool_size` bounds the *intermediate* candidate set
  before ranking, independent of the `related_limit` returned — prevents a
  large seed set from triggering an expensive fan-out.

## 3. Security

- **Read-only Neo4j credentials.** The KG Service connects with a database
  user that has no write privileges, enforced at the Neo4j user/role level —
  not just "the application code happens not to call MERGE/CREATE." Ingestion
  and extraction keep their own separate, write-capable credentials, used
  only by the offline CLIs in `sciagent-KG`, never by this service.
- **Service-to-service auth** via `X-Service-Key` (see architecture doc §6),
  validated against an allowlist stored outside the repo (env var / secret
  manager, never committed — same pattern already established for
  `OPENAI_API_KEY` in `sciagent-KG/.env`, loaded via `python-dotenv`, never
  passed on a command line or logged).
- **Input validation** on every path/query param before it reaches Cypher —
  in particular `entity_type` must validate against the fixed
  `{method, dataset, topic}` set before being used to select a query
  template, mirroring the existing safety pattern in
  `sciagent-KG/queries/entities.py` (label/relationship names come from a
  fixed dict, never from request text, so there is no injection surface even
  though the query is built with an f-string).
- **No secrets or stack traces in error responses** — `500` responses return
  a generic message and a request ID; details go to server-side structured
  logs only.
- **Dependency scanning** in CI (same as the broader product spec's CI
  pipeline, §5 Deployment Requirements in `spec/sciagent_webapp_agent_spec.md`).
- **Write-path credential isolation** (`/v1/ingest-jobs`, architecture doc
  §8.2). The API process (`kg_service.main:app`) is never given
  `KG_WRITE_NEO4J_*` — only the separate ingest worker process
  (`kg_service.worker`) is. This is enforced by which container/process
  receives which env vars in deployment (§6.1), not by application code
  alone, so a bug in `kg_service.main` cannot leak into a write. `/v1/ingest-jobs`
  is additionally gated by its own `KG_SERVICE_WRITE_ALLOWED_KEYS` allowlist,
  disjoint from `KG_SERVICE_ALLOWED_KEYS`.
- **MinIO/Redis are not a new external attack surface for the read path** —
  neither is reachable from, or referenced by, any read endpoint. Only
  `create_ingest_job`/`get_ingest_job_status` (`kg_service/services/ingest.py`)
  and the worker (`kg_service/jobs.py`) touch them.

## 4. Reliability

- `/readyz` fails closed (`503`) if Neo4j is unreachable — load balancers and
  orchestrators must not route traffic to a replica that can't serve real
  requests.
- Request timeouts on every Neo4j call (bounded by the driver's own
  transaction timeout config) — a slow/hung query fails the request rather
  than hanging a worker indefinitely.
- Structured error responses (architecture doc §5) on every failure path,
  including Neo4j connection errors — never an unhandled exception leaking a
  driver stack trace to a caller.
- No automatic retries against Neo4j from inside a single request (retrying
  a read is safe, but silent retries hide real latency/availability
  problems from monitoring) — callers that want retry-on-failure implement
  it themselves with backoff, same as any HTTP client would.

## 5. Testing strategy

### Unit tests

- Response-model serialization: each Pydantic model correctly represents
  the corresponding dataclass (`PaperSummary`, `PaperDetails`, `SearchResult`,
  `RelatedPaper`, `ExpandedResult`) including `None`/optional fields.
- Request validation: empty query strings, out-of-range `limit`/`top_k`,
  invalid `entity_type`, malformed embedding dimension — each produces the
  documented error code, not a 500.
- Error-shape consistency: every error path returns the `{"error": {...}}`
  shape from the architecture doc, asserted once as a shared test helper
  used across all endpoint tests.
- Write path (`tests/unit/test_write_auth.py`, `test_ingest_service.py`,
  `test_jobs.py`): `require_write_service_key` rejects a key that's only in
  the read allowlist; upload validation rejects oversized/empty/malformed/
  missing-`id` files without ever calling MinIO; `create_ingest_job` maps a
  MinIO/Redis failure to `INGEST_STORAGE_UNAVAILABLE`/`INGEST_QUEUE_UNAVAILABLE`
  rather than a bare 500; `run_ingest_job` (the worker task) calls
  `apply_schema`/`load_metadata`/`run_embedding`/`run_validation` with the
  worker's own driver and always closes it, including on failure. All mocked
  — no live Neo4j/MinIO/Redis required.

### Integration tests

- Run against a real (test-database) Neo4j instance seeded with a small
  known fixture graph — not mocks, since the whole point of this service is
  correctly wrapping real Cypher queries (the existing `sciagent-KG` query
  modules are the thing under test here, exercised through the HTTP layer).
- One test per endpoint asserting the full request → Cypher → response round
  trip against the fixture graph, including the `404`/`400` paths (unknown
  paper ID, unknown category, empty seed list).
- A read-only-credential test: attempt a write through the service's Neo4j
  connection in a test and assert it's rejected at the database level, not
  just "the code doesn't expose a write endpoint" — catches a future
  accidental write endpoint or a misconfigured credential.
- **Not yet built**: a full `/v1/ingest-jobs` round trip against live
  MinIO/Redis/Neo4j (upload → worker picks up the job → `GET` reflects
  `finished` with correct counts). Current coverage is unit-level only
  (mocked MinIO/Redis/pipeline functions, see §5 Unit tests) — flagged here
  rather than assumed covered, same convention as `05-kg-service-roadmap.md`'s
  Definition of Done.

### Contract tests

- The generated OpenAPI schema (FastAPI auto-generates this) is checked into
  the repo or published as a build artifact; a contract test fails CI if a
  response shape changes without a version bump — protects downstream
  callers (Retrieval/MCP Service, BFF) from silent breaking changes.

### Load testing

- k6 or Locust, same tooling recommendation as the product-level spec
  (`spec/sciagent_webapp_agent_spec.md` §11.5).
- Profile: mixed traffic matching real usage shape — mostly paper lookups
  and semantic search, occasional graph expansion (the most expensive
  endpoint), rare stats calls.
- Explicitly test the vector-search embedding step under concurrency — it's
  CPU-bound (`sentence-transformers` on CPU unless a GPU is provisioned) and
  is the most likely bottleneck under load, not the Neo4j queries themselves.

## 6. Deployment

- **Containerized**: single Docker image, `uv`-based build (matches
  `sciagent-KG`'s existing tooling), exposing the FastAPI app via Uvicorn.
- **Environment config**: reuses the `NEO4J_URI` / `NEO4J_USERNAME` /
  `NEO4J_PASSWORD` / `NEO4J_DATABASE` convention from
  `sciagent-KG/src/config.py`, with the KG Service pointed at its own
  read-only credential set via the same env var names in its own `.env` /
  deployment secret — plus a new `KG_SERVICE_ALLOWED_KEYS` (or equivalent
  secret-manager reference) for the service-to-service allowlist.
- **Health checks**: `/healthz` as the container liveness probe, `/readyz`
  as the readiness probe — orchestrator (k8s or equivalent) must use both,
  not just one, so a Neo4j outage takes replicas out of rotation without
  restarting them.
- **CI pipeline** (per PR): format/lint, type-check, unit tests, integration
  tests against a disposable Neo4j test container, dependency scan, build
  the image.
- **CD pipeline** (main branch): build versioned image → deploy to staging →
  smoke test the endpoint summary list (§9 of the API spec) → manual/auto
  promote to production → rolling deploy → automatic rollback on failed
  `/readyz` post-deploy.

### 6.1 Write-path deployment: the ingest worker, MinIO, Redis

`/v1/ingest-jobs` (architecture doc §8) needs three extra pieces beyond the
API container, wired together in the root `docker-compose.yml`:

- **`kg-service`** — the same image/Dockerfile as every other section above,
  unchanged command. Its env includes `KG_SERVICE_WRITE_ALLOWED_KEYS`,
  `MINIO_*`, `REDIS_URL` — but **not** `KG_WRITE_NEO4J_*`.
- **`kg-worker`** — the *same* image, different command
  (`uv run python -m kg_service.worker`) and a different env file
  (`sciagent-backend/.env.worker`, not `.env`) containing `KG_WRITE_NEO4J_*`,
  `MINIO_*`, `REDIS_URL` — but no `KG_SERVICE_ALLOWED_KEYS`/`NEO4J_*`
  read-only creds, since it never serves a read request. Scale this
  independently of `kg-service` replica count — it's CPU-bound (embedding)
  and I/O-bound (Neo4j writes), not request-concurrency-bound.
- **`minio`** — S3-compatible object storage for staged uploads. Not
  exposed to any caller outside this deployment; only `kg-service` (PUTs)
  and `kg-worker` (GETs) talk to it.
- **`redis`** — the RQ job queue backing store. Same access pattern: only
  `kg-service` (enqueues) and `kg-worker` (dequeues/executes) talk to it.

None of the four require Neo4j itself to run in the same compose file —
`NEO4J_URI`/`KG_WRITE_NEO4J_URI` point at wherever the graph already lives
(local, staging, or production Neo4j), same as every other section here.

## 7. Exit criteria for this phase

- Every endpoint in the API spec has an integration test against the fixture
  graph.
- Read-only credential enforcement is verified by a test, not just asserted
  in prose.
- The write-path's credential isolation (only `kg-worker` ever receives
  `KG_WRITE_NEO4J_*`) and separate service-key allowlist are verified by a
  live `/v1/ingest-jobs` integration test against MinIO/Redis/Neo4j (§5's
  "Not yet built" gap), not just the current unit-level mocks.
- Load test results confirm the p95 targets in §1 hold at expected launch
  traffic (initial target: enough headroom for the Retrieval/MCP Service and
  BFF combined, sized once those services' expected call volume is known —
  revisit before each service's own launch).
- Staging deployment is reproducible from a clean environment using only the
  documented env vars.
