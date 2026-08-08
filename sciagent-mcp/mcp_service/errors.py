"""KG Service error -> MCP tool error mapping -- specs/02-mcp-architecture.md §7.

Any exception raised inside an @mcp.tool() function is caught by the MCP
server (mcp.server.mcpserver) and turned into a
CallToolResult(content=[TextContent(text=str(exc))], is_error=True) --
that's the SDK's own behavior, not something this service reimplements.
KGServiceError's __str__ carries the KG Service's own {code, message} pair
through into that error text, so a caller sees the same error vocabulary
the KG Service already documents in
sciagent-backend/specs/03-kg-service-api-spec.md, rather than a generic
"tool failed" message.
"""

import httpx

CAPABILITY_NOT_AVAILABLE = "CAPABILITY_NOT_AVAILABLE"
KG_SERVICE_UNAVAILABLE = "KG_SERVICE_UNAVAILABLE"


class KGServiceError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


def error_from_response(response: httpx.Response) -> KGServiceError:
    """Translate a non-2xx KG Service response into a KGServiceError.

    501 is special-cased to CAPABILITY_NOT_AVAILABLE (specs/02-mcp-architecture.md
    §7) -- the KG Service's own NOT_IMPLEMENTED stubs (see
    sciagent-backend/kg_service/errors.py) become a distinct, self-describing
    tool outcome instead of a generic failure, so an agent (or developer) can
    tell "not built yet" apart from "this specific request failed."
    """
    try:
        body = response.json()
        error = body.get("error", {})
        code = error.get("code", "UNKNOWN_ERROR")
        message = error.get("message") or response.text
    except ValueError:
        code, message = "UNKNOWN_ERROR", response.text

    if response.status_code == 501:
        return KGServiceError(
            501,
            CAPABILITY_NOT_AVAILABLE,
            f"This tool's backing KG Service endpoint isn't implemented yet ({message}). "
            "See sciagent-mcp/specs/05-mcp-roadmap.md for what's live.",
        )
    return KGServiceError(response.status_code, code, message)


def error_from_exception(exc: Exception) -> KGServiceError:
    """Connection failure / timeout -- the KG Service never returned a
    response at all, so there's no error.code to pass through."""
    return KGServiceError(503, KG_SERVICE_UNAVAILABLE, f"KG Service request failed: {exc}")
