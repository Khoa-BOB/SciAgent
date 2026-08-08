"""Shared MCPServer instance and process-wide KGServiceClient -- one client
created at Streamable HTTP server startup and reused across every tool call
(specs/02-mcp-architecture.md §4), never one per call. Tool modules
(mcp_service/tools/*.py) import `mcp` from here to register with `@mcp.tool()`,
and call `get_kg_client()` to reach the KG Service.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server.mcpserver import MCPServer

from mcp_service.config import KG_SERVICE_API_KEY, KG_SERVICE_BASE_URL
from mcp_service.kg_client import KGServiceClient

_kg_client: KGServiceClient | None = None


def get_kg_client() -> KGServiceClient:
    if _kg_client is None:
        raise RuntimeError(
            "KGServiceClient not initialized -- the server lifespan hasn't started yet "
            "(are you calling a tool function outside of a running server)?"
        )
    return _kg_client


@asynccontextmanager
async def lifespan(server: MCPServer) -> AsyncIterator[None]:
    global _kg_client
    _kg_client = KGServiceClient(base_url=KG_SERVICE_BASE_URL, api_key=KG_SERVICE_API_KEY)
    try:
        yield
    finally:
        await _kg_client.aclose()
        _kg_client = None


mcp = MCPServer(
    name="sciagent-kg-mcp",
    description=(
        "MCP tools for the SciAgent knowledge graph: paper lookup, semantic/keyword/"
        "filtered search, graph-neighbor expansion, and domain-entity (method/dataset/"
        "topic) browsing. Backed by the KG Service over HTTP -- see specs/."
    ),
    lifespan=lifespan,
)
