"""Inbound Streamable HTTP auth -- specs/02-mcp-architecture.md §6.

Separate from the outbound X-Service-Key this service holds for the KG
Service (mcp_service/kg_client.py) -- this middleware checks the Agent
Orchestrator's own credential on the way in. Two independent credentials,
same "restricted, non-shared trust" pattern the KG Service already applies
between itself and Neo4j.
"""

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from mcp_service.config import MCP_ALLOWED_KEYS

# /healthz is a public liveness probe -- same "no auth on health checks"
# convention the KG Service uses for /healthz and /readyz
# (sciagent-backend/specs/02-kg-service-architecture.md §6).
EXEMPT_PATHS = {"/healthz"}


class ServiceKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        key = _extract_bearer_token(request)
        if not key or key not in MCP_ALLOWED_KEYS:
            return JSONResponse(
                {"error": {"code": "UNAUTHENTICATED", "message": "Missing or invalid credentials."}},
                status_code=401,
            )
        return await call_next(request)


def _extract_bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[len("bearer "):].strip()
    return None
