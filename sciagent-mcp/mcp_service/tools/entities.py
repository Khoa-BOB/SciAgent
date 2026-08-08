"""specs/03-mcp-tool-spec.md §9-10."""

from mcp_service.app import get_kg_client, mcp


@mcp.tool()
async def list_entities(entity_type: str, query: str | None = None, limit: int = 20) -> dict:
    """Browse or search known methods, datasets, or research topics by
    name. entity_type must be one of 'method', 'dataset', 'topic'. Use to
    resolve a loose term (e.g. 'the CLIP-like approach') to a canonical
    entity name before calling find_papers_by_entity."""
    return await get_kg_client().list_entities(entity_type, query, limit)


@mcp.tool()
async def find_papers_by_entity(entity_type: str, normalized_name: str, limit: int = 20) -> dict:
    """Find papers that use a given method/dataset or study a given topic.
    entity_type must be one of 'method', 'dataset', 'topic'. Use
    list_entities first if you don't already have the exact normalized
    entity name."""
    return await get_kg_client().papers_for_entity(entity_type, normalized_name, limit)
