"""specs/03-mcp-tool-spec.md §11."""

from mcp_service.app import get_kg_client, mcp


@mcp.tool()
async def get_kg_stats() -> dict:
    """Get corpus-level statistics: total papers, authors, categories, and
    domain-entity counts by type. Use for meta-questions about the corpus,
    not for answering research questions."""
    return await get_kg_client().get_stats()
