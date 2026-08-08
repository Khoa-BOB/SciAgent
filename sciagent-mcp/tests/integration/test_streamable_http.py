"""End-to-end MCP protocol round trip over the real Streamable HTTP app --
specs/04-mcp-nfr-testing-deployment.md §5 ("MCP protocol compliance check").

Uses TestClient as a context manager (`with TestClient(app) as client:`) so
the ASGI lifespan actually runs -- the MCP SDK's StreamableHTTPSessionManager
needs that to initialize its task group, and a bare `TestClient(app)` without
the lifespan raises "Task group is not initialized" on the first request.
No live KG Service or Neo4j is needed here: tools/list and the
initialize/initialized handshake never call out to the KG Service, they only
exercise the MCP protocol layer and this service's own auth middleware.

Each test calls create_app() fresh rather than reusing mcp_service.server's
module-level `app` singleton: a StreamableHTTPSessionManager's run() can only
be entered once per instance (it errors on a second lifespan startup), and
each `with TestClient(...)` block runs the lifespan once.
"""

from starlette.testclient import TestClient

import mcp_service.auth as auth_module
from mcp_service.server import create_app

_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
    "Host": "localhost:8100",
}


def test_healthz_needs_no_auth() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_mcp_endpoint_rejects_missing_auth() -> None:
    with TestClient(create_app()) as client:
        response = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            headers=_HEADERS,
        )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_mcp_initialize_and_tools_list_round_trip(monkeypatch) -> None:
    monkeypatch.setattr(auth_module, "MCP_ALLOWED_KEYS", {"test-key"})
    headers = {**_HEADERS, "Authorization": "Bearer test-key"}

    with TestClient(create_app()) as client:
        init_response = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "pytest", "version": "0"},
                },
            },
            headers=headers,
        )
        assert init_response.status_code == 200
        session_id = init_response.headers["mcp-session-id"]
        session_headers = {**headers, "mcp-session-id": session_id}

        initialized_response = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            headers=session_headers,
        )
        assert initialized_response.status_code == 202  # notification, no JSON-RPC response body

        list_response = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            headers=session_headers,
        )

    assert list_response.status_code == 200
    body = list_response.text
    tool_names = {
        "get_paper",
        "get_paper_entities",
        "search_papers_semantic",
        "search_papers_keyword",
        "search_papers_by_author",
        "search_papers_by_category",
        "search_papers_by_year",
        "expand_paper_neighbors",
        "list_entities",
        "find_papers_by_entity",
        "get_kg_stats",
    }
    for name in tool_names:
        assert f'"name":"{name}"' in body
