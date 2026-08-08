# SciAgent MCP Server — Non-Functional Requirements, Testing, Deployment

Phases 2 (design), 4 (verification), and 5 (deployment) of the SDLC (see
[`00-overview.md`](00-overview.md)).

## 1. Performance targets

Each tool's latency budget is the KG Service's own p95 target
(`sciagent-backend/specs/04-kg-service-nfr-testing-deployment.md` §1) plus a
small fixed overhead for the MCP hop itself:

| Tool | KG Service p95 basis | MCP tool p95 target |
|---|---:|---:|
| `get_paper` | < 100ms | < 150ms |
| `get_paper_entities` | (new, small aggregate query) | < 150ms |
| `search_papers_keyword` | < 300ms | < 350ms |
| `search_papers_semantic` | < 500ms | < 550ms |
| `search_papers_by_author`/`by_category`/`by_year` | < 300ms (indexed match) | < 350ms |
| `expand_paper_neighbors` | < 800ms | < 900ms |
| `list_entities` / `find_papers_by_entity` | (new, indexed lookup) | < 250ms |
| `get_kg_stats` | < 200ms | < 250ms |

The MCP-hop overhead (~50-100ms) covers the `httpx` request, MCP protocol
serialization, and Streamable HTTP framing — no additional model calls or
heavy computation happen inside this service. Re-baseline once the KG
Service's own Sprint 2/3 endpoints (see `05-mcp-roadmap.md`) are actually
implemented and measured, rather than relying on the KG Service's *target*
numbers indefinitely.

## 2. Scalability

- Stateless — horizontal scaling is adding replicas behind a load balancer,
  same as the KG Service.
- One shared `httpx.AsyncClient` per process (§4 of the architecture doc);
  size its internal connection pool relative to expected concurrent tool
  calls per replica.
- This service adds no new caps beyond what the KG Service already
  enforces (`limit`/`top_k`/`pool_size`) — it validates types/ranges before
  the HTTP call but does not need its own separate cap table to keep in
  sync with the KG Service's.

## 3. Security

- **No Neo4j credentials anywhere in this service** — enforced
  architecturally, not just by convention (§9 of the architecture doc).
- **Two independent service credentials** (§6 of the architecture doc):
  outbound `KG_SERVICE_API_KEY` to the KG Service, inbound `MCP_ALLOWED_KEYS`
  allowlist for the Agent Orchestrator. Neither is ever logged; both are
  loaded from environment/secret manager, same pattern as
  `sciagent-KG/.env`'s `OPENAI_API_KEY` handling.
- **Tool argument validation** before any outbound HTTP call — malformed
  input fails fast with a clear MCP tool error instead of reaching the KG
  Service and producing a less legible error.
- **Output size limits**: list-shaped tool outputs never exceed the KG
  Service's own server-enforced caps (this service doesn't introduce a
  separate limit, but also doesn't need to guard against an unbounded
  response — the KG Service already guarantees a bound).
- **No secrets or stack traces in tool error content** — matches the KG
  Service's own rule (§7 of the architecture doc); unexpected exceptions
  produce a generic `KG_SERVICE_UNAVAILABLE` error, full detail goes to
  server-side structured logs only.
- **Dependency scanning** in CI, same as the broader product spec's CI
  pipeline requirement.

## 4. Reliability

- No automatic retries against the KG Service from inside a single tool
  call (matches the KG Service's own "no automatic retries" rule) — a
  transient KG Service failure surfaces as a tool error; retry-with-backoff
  is the Agent Orchestrator's responsibility, same as it would be for any
  other tool call.
- Request timeouts on every KG Service call, sized from §1's targets with
  headroom — a hung KG Service call fails the tool call rather than
  blocking a worker indefinitely.
- `501 NOT_IMPLEMENTED` from the KG Service is handled explicitly (§7 of
  the architecture doc) — never surfaces as an unhandled exception.

## 5. Testing strategy

### Unit tests

- One test per tool: successful call (mocked `KGServiceClient` returns a
  fixture response, tool output matches the schema in
  `03-mcp-tool-spec.md`), each documented error path (mocked client raises
  `KGServiceError` with each relevant code), and input validation (missing
  required field, wrong type, out-of-range value).
- `KGServiceClient` itself: request construction (correct method, path,
  params, `X-Service-Key` header) against a mocked `httpx` transport —
  doesn't need a real KG Service running.
- Error-mapping consistency: every `KGServiceError` produces the documented
  MCP tool error shape, asserted once as a shared test helper reused across
  all tool tests (mirrors the KG Service's own shared error-shape test
  helper).

### Integration tests

- Run a real `sciagent-backend` instance (against a fixture/dev Neo4j) and
  this service together; call each tool end-to-end via an MCP test client.
- Cover the success path and the KG Service's documented error paths
  (unknown paper ID, unknown category, empty seed list, unknown entity
  type) through the full stack, not just the KG Service's own integration
  tests in isolation.
- A `501`-handling test: point this service at a KG Service build where a
  given endpoint is still a stub, assert the tool returns
  `CAPABILITY_NOT_AVAILABLE` rather than crashing — keeps the "partial
  backend is a safe state" guarantee from `00-overview.md` actually tested,
  not just asserted in prose.

### Protocol compliance

- Use the `mcp` SDK's client (or MCP Inspector) to connect over Streamable
  HTTP, list tools, and confirm the advertised JSON schemas match
  `03-mcp-tool-spec.md` exactly (no undocumented fields, correct
  required/optional markers).
- Call a representative tool from each group (§1-5 of the requirements doc)
  through the protocol layer, not just through direct Python function
  calls, to catch serialization issues the unit tests wouldn't.

### Load testing

- Same tooling recommendation as the product-level and KG Service specs
  (k6/Locust). Profile: mixed tool-call traffic weighted toward
  `get_paper` and `search_papers_semantic` (matches expected real usage
  shape from the KG Service's own load-test profile).
- This service is not expected to be the bottleneck — verify that under
  load, added latency stays within the "small fixed overhead" budget in §1
  rather than growing with concurrency (would indicate a connection-pool
  sizing problem, not a KG Service problem).

## 6. Deployment

- **Containerized**: single Docker image, `uv`-based build, exposing the
  FastMCP Streamable HTTP app via its ASGI server — matches
  `sciagent-backend`'s Dockerfile pattern but does **not** need to `COPY`
  `sciagent-KG` (this service has no dependency on it), only its own source.
- **Environment config**:
  - `KG_SERVICE_BASE_URL` — base URL of the KG Service (e.g.
    `http://sciagent-backend:8000`).
  - `KG_SERVICE_API_KEY` — this service's own entry in the KG Service's
    `KG_SERVICE_ALLOWED_KEYS` allowlist.
  - `MCP_ALLOWED_KEYS` — comma-separated allowlist for inbound Agent
    Orchestrator connections.
  - `HOST` / `PORT` — Streamable HTTP bind address.
- **Health checks**: this service is stateless and has no database of its
  own, so a liveness check is just "the process is running and can reach
  the KG Service's `/readyz`." Expose a lightweight non-MCP health route
  alongside the Streamable HTTP app (FastMCP supports mounting additional
  ASGI routes) so container orchestration doesn't need an MCP client just
  to check liveness.
- **CI pipeline** (per PR): format/lint, type-check, unit tests, integration
  tests against a disposable KG Service + Neo4j test container, dependency
  scan, build the image.
- **CD pipeline** (main branch): build versioned image → deploy to staging
  → smoke test the tool list (§ summary in `03-mcp-tool-spec.md`) → promote
  → rolling deploy → automatic rollback on failed health check.
- **Deployment order**: this service depends on the KG Service being
  reachable at startup-adjacent time but does not hard-fail if it's briefly
  unavailable (tool calls fail individually with `KG_SERVICE_UNAVAILABLE`
  rather than the whole process refusing to start) — allows independent
  deploys/restarts of the two services.

## 7. Exit criteria for this phase

- Every tool has a unit test and an integration test covering its success
  path and every documented error path, including `CAPABILITY_NOT_AVAILABLE`.
- Protocol-compliance check passes against a real MCP client.
- Load test confirms the added-latency budget in §1 holds at expected
  launch traffic.
- Staging deployment is reproducible from a clean environment using only
  the documented env vars, and works standing next to a `sciagent-backend`
  instance deployed independently.
