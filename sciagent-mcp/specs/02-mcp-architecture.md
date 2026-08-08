# SciAgent MCP Server — Architecture and Technical Design

Phase 2 of the SDLC (see [`00-overview.md`](00-overview.md)).

## 1. Service boundary

```text
                    Agent Orchestrator
                          |
                          | MCP over Streamable HTTP
                          | (Authorization: Bearer <mcp session key>)
                          v
                +---------------------+
                |    sciagent-mcp     |
                | (FastMCP, stateless) |
                +---------------------+
                          |
                          | HTTPS + X-Service-Key
                          v
                +---------------------+
                |   sciagent-backend   |
                |    ("KG Service")    |
                +---------------------+
                          |
             imports as a library (same process, KG Service side)
                          v
        sciagent-KG: queries/*.py, src/retrieval/*.py
                          |
                          v
                Neo4j (read-only credentials)
```

`sciagent-mcp` talks to the KG Service exactly the way any other internal
HTTP client would — it has no special access. It never imports `sciagent-KG`
and never opens a connection to Neo4j.

## 2. Why the official `mcp` Python SDK + FastMCP

- Matches the existing stack: Python + `uv`, same tooling as `sciagent-KG`
  and `sciagent-backend` — no second language/runtime to operate.
- `FastMCP` (from the `mcp` package) provides decorator-based tool
  registration with automatic JSON-schema generation from type hints —
  mirrors how `sciagent-backend` gets automatic OpenAPI generation from
  FastAPI/Pydantic; the two services follow the same "schema from code,
  not hand-maintained" principle.
- `FastMCP` supports `transport="streamable-http"` natively — no separate
  ASGI wiring needed for the chosen transport (see §3).

## 3. Transport: Streamable HTTP only

No stdio transport. This service is a standing, network-reachable component
called by the Agent Orchestrator process (per
`spec/sciagent_webapp_agent_spec.md` §4.1's component diagram: `MCP Client
-> MCP Server` is a network hop, not a subprocess pipe) — stdio would only
make sense if the orchestrator spawned this server as a local child process,
which is not the deployment model here (see `04-mcp-nfr-testing-deployment.md`
§6).

Local development and manual testing use the same Streamable HTTP endpoint
via MCP Inspector or a short Python script using the `mcp` SDK's client —
no separate code path.

## 4. Process and connection model

- One shared `httpx.AsyncClient` per process, created at startup, reused
  across all tool calls — mirrors the KG Service's own "one driver per
  process" rule (`sciagent-backend/specs/02-kg-service-architecture.md` §3).
  Never open a new client per request.
- The client is configured with a request timeout matching the KG Service's
  own NFR targets plus headroom (see `04-mcp-nfr-testing-deployment.md` §1)
  — a hung KG Service call fails the tool call rather than hanging
  indefinitely.
- Stateless: no per-request in-process state, no session affinity needed,
  so this service can run as multiple replicas behind a load balancer
  immediately, same as the KG Service.

## 5. `kg_client` design

`mcp_service/kg_client.py` is a thin async wrapper, one method per KG
Service endpoint actually used (see `03-mcp-tool-spec.md` for the full
list), e.g.:

```python
class KGServiceClient:
    def __init__(self, base_url: str, api_key: str, client: httpx.AsyncClient): ...

    async def get_paper(self, arxiv_id: str) -> dict: ...
    async def get_paper_entities(self, arxiv_id: str) -> dict: ...
    async def search_semantic(self, q: str, top_k: int) -> dict: ...
    async def search_fulltext(self, q: str, limit: int) -> dict: ...
    async def search_by_author(self, name: str, limit: int) -> dict: ...
    async def search_by_category(self, code: str, limit: int) -> dict: ...
    async def search_by_year(self, start_year: int, end_year: int | None, limit: int) -> dict: ...
    async def expand_graph(self, paper_ids: list[str], query_embedding: list[float] | None,
                            related_limit: int, pool_size: int) -> dict: ...
    async def list_entities(self, entity_type: str, q: str | None, limit: int) -> dict: ...
    async def papers_for_entity(self, entity_type: str, normalized_name: str, limit: int) -> dict: ...
    async def get_stats(self) -> dict: ...
```

Every method sets `X-Service-Key` from config (§6), does **not** retry
automatically (matches the KG Service's own "no automatic retries" NFR —
`sciagent-backend/specs/04-kg-service-nfr-testing-deployment.md` §4; a
caller/orchestrator that wants retry-with-backoff implements it itself),
and raises `KGServiceError` (see §7) on any non-2xx response rather than
returning a partially-parsed result.

Tool handlers (`mcp_service/tools/*.py`) call `kg_client`, translate the
KG Service's JSON shape 1:1 into the tool's declared output schema
(`03-mcp-tool-spec.md`), and catch `KGServiceError` to produce a structured
MCP tool error (§7). No tool handler does its own HTTP calls directly.

## 6. Authentication — two independent credentials

This service sits between two trust boundaries and holds a distinct
credential for each direction, matching the "restricted credentials, no
shared trust" principle already used between the KG Service and Neo4j:

- **Outbound** (`sciagent-mcp` → KG Service): a static `X-Service-Key`
  value from `KG_SERVICE_API_KEY`, one of the KG Service's own allowlisted
  keys (`sciagent-backend/specs/02-kg-service-architecture.md` §6). This
  service is just another entry in that allowlist.
- **Inbound** (Agent Orchestrator → `sciagent-mcp`): a static bearer
  credential checked against `MCP_ALLOWED_KEYS`, an allowlist local to this
  service — same pattern as the KG Service's own `require_service_key`
  dependency, applied here to incoming Streamable HTTP connections instead
  of incoming REST requests.

No end-user auth here — that remains the BFF's responsibility
(`spec/sciagent_webapp_agent_spec.md` §4.2). This service authenticates
*services*, not end users, at both boundaries.

## 7. Error model — mapping KG Service errors to MCP tool errors

The KG Service returns structured errors:
```json
{"error": {"code": "PAPER_NOT_FOUND", "message": "...", "details": {}}}
```

`kg_client` raises `KGServiceError(status_code, code, message)` for any
non-2xx response. Tool handlers catch this and return an MCP tool error
result (`isError=True`) whose content carries the same `code`/`message` —
the agent orchestrator gets the identical error vocabulary the KG Service
already documents, no re-translation layer to keep in sync.

Special case: **`501` / `NOT_IMPLEMENTED`**. Rather than surfacing this as
a generic failure, tool handlers detect it and return a distinct, clearly
worded error (e.g. `"code": "CAPABILITY_NOT_AVAILABLE"`) so an agent (or a
developer reading logs) can tell "this KG Service endpoint isn't built yet"
apart from "this specific request failed." This directly supports the
full-contract-now decision in `00-overview.md` — partial backend
implementation must be a visible, self-describing state, not a silent or
confusing one.

| KG Service outcome | MCP tool outcome |
|---|---|
| `2xx` | Normal tool result, translated to the declared output schema |
| `4xx` with a documented `error.code` | Tool error, same `code`/`message` passed through |
| `501 NOT_IMPLEMENTED` | Tool error, `code: CAPABILITY_NOT_AVAILABLE`, message names the tool and points to `05-mcp-roadmap.md` |
| `5xx` (unexpected) / connection failure / timeout | Tool error, `code: KG_SERVICE_UNAVAILABLE`, generic message — never leak a raw stack trace or httpx exception text to the caller |

## 8. Request/response conventions

- Every tool's output is a JSON object (never a bare list) — list-shaped
  results use `{"items": [...], "count": <int>}`, matching the KG Service's
  own list-response convention
  (`sciagent-backend/specs/02-kg-service-architecture.md` §4) so callers
  don't have to learn two different shapes for "a list of things."
- `limit`/`top_k`/`pool_size`-style parameters are optional with documented
  defaults; this service does not re-clamp them (the KG Service already
  enforces server-side caps regardless of what's requested) but does
  validate they're the right type/sign before making the HTTP call, so a
  malformed tool call fails fast with a clear message instead of producing
  a confusing KG Service `422`.

## 9. Exit criteria for this phase

- Every tool in `03-mcp-tool-spec.md` maps to exactly one KG Service
  endpoint from `sciagent-backend/specs/03-kg-service-api-spec.md`.
- The error model and the two-credential auth model are fixed before
  implementation starts — changing them later affects every existing
  Agent Orchestrator integration.
- No component of this design requires a Neo4j credential, a `sciagent-KG`
  import, or knowledge of Cypher — verified by the dependency list in
  `mcp_service/pyproject.toml` containing no `neo4j` package.
