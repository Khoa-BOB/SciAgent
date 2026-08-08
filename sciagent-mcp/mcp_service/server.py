"""Entrypoint -- specs/02-mcp-architecture.md §3 (Streamable HTTP only, no
stdio) and specs/04-mcp-nfr-testing-deployment.md §6.

Run locally with: uv run python -m mcp_service.server
"""

from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse

import mcp_service.tools.entities
import mcp_service.tools.graph
import mcp_service.tools.papers
import mcp_service.tools.search
import mcp_service.tools.stats  # noqa: F401
from mcp_service.app import mcp
from mcp_service.auth import ServiceKeyMiddleware
from mcp_service.config import (
    HOST,
    MCP_ALLOWED_HOSTS,
    MCP_ALLOWED_ORIGINS,
    PORT,
    validate_config,
)


async def healthz(request: Request) -> JSONResponse:
    # Liveness only, no KG Service call -- matches the KG Service's own
    # /healthz semantics (sciagent-backend/specs/03-kg-service-api-spec.md §1).
    # No inbound auth on this route either, same convention.
    return JSONResponse({"status": "ok"})


def _transport_security() -> TransportSecuritySettings | None:
    # Below MCP_ALLOWED_HOSTS is unset, streamable_http_app(host=HOST) already
    # auto-enables DNS-rebinding protection scoped to 127.0.0.1/localhost --
    # fine for local dev, but production behind a real hostname or reverse
    # proxy needs the extra hosts/origins explicitly allowed or every request
    # 421s (mcp_service/config.py).
    if not MCP_ALLOWED_HOSTS:
        return None
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[*MCP_ALLOWED_HOSTS, "127.0.0.1:*", "localhost:*", "[::1]:*"],
        allowed_origins=[*MCP_ALLOWED_ORIGINS, "http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"],
    )


def create_app() -> Starlette:
    app = mcp.streamable_http_app(host=HOST, transport_security=_transport_security())
    app.router.add_route("/healthz", healthz, methods=["GET"])
    app.add_middleware(ServiceKeyMiddleware)
    return app


app = create_app()


def main() -> None:
    validate_config()

    import uvicorn

    uvicorn.run(app, host=HOST, port=PORT)


if __name__ == "__main__":
    main()
