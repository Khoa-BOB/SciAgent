"""specs/02-mcp-architecture.md §6 -- inbound Streamable HTTP auth.

Exercised against a tiny standalone Starlette app rather than the real
mcp_service.app.app, so this doesn't depend on the MCP session manager's
lifespan (mirrors kg_service's own auth-only unit tests).
"""

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

import mcp_service.auth as auth_module
from mcp_service.auth import ServiceKeyMiddleware


async def _ok(request):
    return JSONResponse({"ok": True})


async def _healthz(request):
    return JSONResponse({"status": "ok"})


def _app(monkeypatch, allowed_keys: set[str]) -> Starlette:
    monkeypatch.setattr(auth_module, "MCP_ALLOWED_KEYS", allowed_keys)
    app = Starlette(routes=[Route("/mcp", _ok, methods=["POST"]), Route("/healthz", _healthz, methods=["GET"])])
    app.add_middleware(ServiceKeyMiddleware)
    return app


def test_missing_auth_header_rejected(monkeypatch) -> None:
    client = TestClient(_app(monkeypatch, {"good-key"}))

    response = client.post("/mcp")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_wrong_key_rejected(monkeypatch) -> None:
    client = TestClient(_app(monkeypatch, {"good-key"}))

    response = client.post("/mcp", headers={"Authorization": "Bearer wrong-key"})

    assert response.status_code == 401


def test_correct_key_accepted(monkeypatch) -> None:
    client = TestClient(_app(monkeypatch, {"good-key"}))

    response = client.post("/mcp", headers={"Authorization": "Bearer good-key"})

    assert response.status_code == 200


def test_healthz_exempt_from_auth(monkeypatch) -> None:
    client = TestClient(_app(monkeypatch, {"good-key"}))

    response = client.get("/healthz")

    assert response.status_code == 200


def test_malformed_authorization_header_rejected(monkeypatch) -> None:
    client = TestClient(_app(monkeypatch, {"good-key"}))

    response = client.post("/mcp", headers={"Authorization": "good-key"})

    assert response.status_code == 401
