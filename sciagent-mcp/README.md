# sciagent-mcp

MCP server exposing the SciAgent knowledge graph to agents, over Streamable
HTTP. Full spec set lives in [`specs/`](specs/00-overview.md) — start there
for the why/what before changing anything here.

This service is an HTTP **client** of the KG Service (`sciagent-backend`)
only — it never touches Neo4j or imports anything from `sciagent-KG`.

## Layout

```text
sciagent-mcp/
├── mcp_service/
│   ├── server.py       -- entrypoint: builds the Starlette app, runs uvicorn
│   ├── app.py            -- shared MCPServer instance + process-wide KGServiceClient
│   ├── config.py           -- env vars
│   ├── kg_client.py          -- async httpx client, one method per KG Service endpoint
│   ├── errors.py               -- KG Service error -> KGServiceError mapping
│   ├── auth.py                   -- inbound Bearer-token check
│   └── tools/                      -- one file per tool group, all 11 MCP tools
└── tests/
    ├── unit/            -- no KG Service or Neo4j required (mocked kg_client)
    └── integration/       -- real MCP protocol round trip over Streamable HTTP
```

## Running locally

```bash
cp .env.example .env   # fill in KG_SERVICE_API_KEY and MCP_ALLOWED_KEYS
uv sync
uv run python -m mcp_service.server
```

Requires a reachable KG Service at `KG_SERVICE_BASE_URL` (default
`http://localhost:8000`) — see `sciagent-backend/README.md` to run one
locally. `/healthz` needs no auth; the `/mcp` Streamable HTTP endpoint
requires `Authorization: Bearer <one of MCP_ALLOWED_KEYS>`.

## Testing

```bash
uv run pytest tests/unit          # mocked KGServiceClient, no network
uv run pytest tests/integration   # real MCP protocol round trip, still no live KG Service needed
uv run ruff check .
uv run mypy mcp_service
```

## Current status

All 11 tools in `specs/03-mcp-tool-spec.md` are implemented against the full
KG Service contract. A tool whose backing KG Service endpoint isn't
implemented yet (see `sciagent-backend/README.md`'s current-status section)
returns a `CAPABILITY_NOT_AVAILABLE` tool error rather than crashing — see
`specs/05-mcp-roadmap.md` for what's live on the KG Service side.

## Docker

Build from the **repository root** (parent of `sciagent-mcp`):

```bash
docker build -f sciagent-mcp/Dockerfile -t sciagent-kg-mcp .
```
