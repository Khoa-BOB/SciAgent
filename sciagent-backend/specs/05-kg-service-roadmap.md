# KG Service — Delivery Roadmap

Phases 3 (implementation) and 6 (operation) of the backend SDLC (see
[`00-overview.md`](00-overview.md)).

## Sprint 1 — Skeleton and paper lookup

- Repository scaffold: `sciagent-backend/` FastAPI app, `uv` project,
  dependency on `sciagent-KG` as a path dependency.
- `/healthz`, `/readyz`.
- `GET /v1/papers/{arxiv_id}`, `GET /v1/papers/{arxiv_id}/embedding`.
- Error model + `X-Service-Key` auth middleware (architecture doc §5, §6).
- CI: lint, type-check, unit tests.

**Exit**: a deployed staging instance answers paper lookups with the correct
error model on miss.

## Sprint 2 — Search

- `GET /v1/search/fulltext`
- `GET /v1/search/semantic`, `POST /v1/search/semantic/by-embedding`
- `GET /v1/search/by-author`, `GET /v1/search/by-category`,
  `GET /v1/search/by-year`
- Integration tests against a fixture Neo4j instance for every search
  endpoint, including empty-result and validation-error paths.

**Exit**: every Story in §3 of `01-kg-service-requirements.md` for search is
covered by a passing integration test.

## Sprint 3 — Graph expansion and domain entities

- `POST /v1/graph/expand`
- `GET /v1/papers/{arxiv_id}/entities`
- `GET /v1/entities/{entity_type}`, `GET /v1/entities/{entity_type}/{normalized_name}/papers`
- New read-side Cypher templates added to `sciagent-KG/queries/entities.py`
  (additive only, per architecture doc §8).
- `GET /v1/stats`

**Exit**: full endpoint summary (API spec §9) is implemented and integration
tested.

## Sprint 4 — Hardening and production readiness

- Load testing against the p95 targets in the NFR doc §1; tune Neo4j
  connection pool size and Uvicorn worker count based on results.
- Read-only-credential enforcement test (NFR doc §5).
- Contract test wired into CI (OpenAPI schema diff check).
- Security review: confirm no write path exists, confirm service-key
  allowlist is sourced from a secret manager, confirm dependency scan is
  clean.
- Production deployment, dashboards (request rate, p95/p99 latency by
  endpoint, error rate by code, Neo4j query latency), alerting on `/readyz`
  failures.

**Exit**: matches the exit criteria in `04-kg-service-nfr-testing-deployment.md` §7.

## Sprint 5 — Ingestion write path (`/v1/ingest-jobs`)

Added after Sprint 4, in response to a concrete need (adding new papers
without CLI/terminal access) rather than being in the original plan — see
`01-kg-service-requirements.md` Story 1.8 and `02-kg-service-architecture.md`
§8 for the full design.

- `POST /v1/ingest-jobs` (upload + validate + stage to MinIO + enqueue),
  `GET /v1/ingest-jobs/{job_id}` (poll status) — both gated by a separate
  `KG_SERVICE_WRITE_ALLOWED_KEYS` allowlist.
- `kg_service/jobs.py` + `kg_service/worker.py` — a separate worker
  process holding the one read-write Neo4j credential in this codebase
  besides `sciagent-KG`'s own CLIs, built from `KG_WRITE_NEO4J_*` env vars
  the API process never reads.
- `docker-compose.yml` (repo root) wiring `minio`, `redis`, `kg-service`,
  `kg-worker`.
- Unit tests for auth, upload validation, MinIO/Redis failure handling, and
  the worker task (`tests/unit/test_write_auth.py`,
  `test_ingest_service.py`, `test_jobs.py`) — all mocked, no live
  MinIO/Redis/Neo4j.

**Not done yet** (see NFR doc §5, §7):
- A live integration test exercising the full upload → worker → status
  round trip against real MinIO/Redis/Neo4j.
- Load testing `POST /v1/ingest-jobs`'s synchronous path (§1 of the NFR doc
  sets a target but it hasn't been measured).
- A frontend upload UI — this sprint is the API only.

**Exit**: a live deployment can add papers via `POST /v1/ingest-jobs` end to
end, verified manually against a real MinIO/Redis/Neo4j, with the two gaps
above tracked as explicit follow-up rather than assumed covered.

## Sprint 6 — Optional extraction follow-up + acronym-merge fallback

Closes two gaps identified while reasoning through what happens to a newly
ingested paper's entities: (1) `/v1/ingest-jobs` had no way to also extract
entities for the papers it loaded, and (2) even a full manual `resolve` run
had a measured 0% merge recall on acronym/expansion pairs (`sciagent-KG/specs/04-roadmap.md`
Near-term #4), so a new paper's "CNN" would never join an existing
"convolutional neural network" node either way.

- `POST /v1/ingest-jobs` gains an optional `run_extraction` form field
  (default `false`, never automatic) — see `02-kg-service-architecture.md`
  §8.4–§8.5 and `03-kg-service-api-spec.md` §8.
- `kg_service/jobs.py:_run_extraction_followup` — extracts entities for
  exactly this job's papers, but re-resolves against `sciagent-KG`'s full
  `data/extraction/shards/` directory (not just the new shard) so new
  mentions can cluster into already-existing canonical entities, then
  filters `merge` back down to only this job's rows before writing. A
  failure here is caught and reported as `result.extraction.error`, never
  raised — ingestion has already committed by that point.
- `sciagent-KG/src/extraction/resolve.py`: an acronym-detection fallback in
  `cluster_names()` (`_initials`/`_is_acronym_token`/`_acronym_fallback_match`)
  — checked only after cosine similarity already failed, so it's additive,
  not a change to the existing threshold behavior. Directly targets the
  measured 0% merge recall on acronym/expansion pairs; verified via
  `sciagent-KG/tests/test_resolve.py`'s unit tests (fake embedding model,
  both merge directions, and a negative case proving unrelated names still
  don't merge) — **not yet re-verified against the real corpus and
  `src.evaluation.cli entities`'s merge-recall metric**, since that requires
  a live Neo4j with the real 36k-paper corpus loaded, which this environment
  doesn't have. Re-running `resolve` + `merge` against the real corpus and
  re-checking `cli.py entities`'s merge recall (per `04-roadmap.md`'s
  original Near-term #4 wording) is the concrete next step to close that
  loop.
- `sciagent-backend` now depends on `spacy`/`openai`/`tqdm` (transitively
  needed by `src.extraction.*`); `Dockerfile` downloads `en_core_web_sm` at
  build time so `kg-worker` can run candidate-phrase extraction.

**Not done yet**:
- Real-corpus verification of the acronym fallback's merge-recall
  improvement (see above) — the concrete, cheap, already-specified next step
  from `04-roadmap.md`.
- A live integration test for `run_extraction=true` against a real LLM
  backend, MinIO, Redis, and Neo4j (extends Sprint 5's same gap).
- No standalone extraction-only endpoint (e.g. `/v1/extraction-jobs`) —
  extraction is only reachable bundled into an ingest job, per Story 1.8's
  explicit out-of-scope note in `01-kg-service-requirements.md` §4.

## Definition of Done (per endpoint)

An endpoint is done only when:

- It matches its entry in `03-kg-service-api-spec.md` exactly (request
  shape, response shape, error codes).
- It has a unit test for request validation and a fixture-backed integration
  test for the success path and every documented error path.
- It enforces its documented `limit`/`top_k`/`pool_size` cap server-side,
  verified by a test that requests above the cap and asserts it's clamped or
  rejected, not silently honored.
- Its latency is within the NFR target under the load-test profile.
- It appears in the generated OpenAPI schema with no undocumented fields.

## After this service

Once the KG Service reaches Sprint 4's exit criteria, the next spec to write
(per `00-overview.md`'s planned-services table) is the **Retrieval/MCP
Service** — it wraps this API (plus reranking) as MCP tools for the agent
orchestrator, matching the MCP tool list already sketched in
`spec/sciagent_webapp_agent_spec.md` §4.2 (`search_papers_semantic`,
`search_papers_keyword`, `get_paper`, `expand_paper_neighbors`, etc.). That
spec should be written only after this one is actually implemented, so its
architecture reflects the KG Service's real latency/error characteristics
rather than assumed ones.
