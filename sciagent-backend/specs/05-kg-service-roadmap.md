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

**Exit**: full endpoint summary (API spec §8) is implemented and integration
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
