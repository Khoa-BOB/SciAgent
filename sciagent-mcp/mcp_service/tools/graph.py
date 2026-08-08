"""specs/03-mcp-tool-spec.md §8.

query_embedding is deliberately not exposed as a tool parameter -- no MCP
tool in this service produces an embedding for an agent to pass through
(specs/01-mcp-requirements.md exclusions), so this always ranks by shared
authors/categories rather than similarity to a query.
"""

from mcp_service.app import get_kg_client, mcp


@mcp.tool()
async def expand_paper_neighbors(paper_ids: list[str], related_limit: int = 5, pool_size: int = 20) -> dict:
    """Given one or more seed papers, find related papers via shared authors
    or shared categories, ranked by relevance. Use for 'find related work'
    or 'what else should I read' questions."""
    return await get_kg_client().expand_graph(paper_ids, None, related_limit, pool_size)
