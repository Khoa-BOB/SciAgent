"""specs/03-mcp-tool-spec.md §1-2."""

from mcp_service.app import get_kg_client, mcp


@mcp.tool()
async def get_paper(arxiv_id: str) -> dict:
    """Get full metadata for a single paper by its arXiv ID -- title,
    abstract, authors, categories, journal, DOI, update date, and version
    history."""
    return await get_kg_client().get_paper(arxiv_id)


@mcp.tool()
async def get_paper_entities(arxiv_id: str) -> dict:
    """Get the methods, datasets, and research topics extracted for a
    paper, with confidence scores. Returns empty lists if the paper has no
    extracted entities -- that is a valid outcome, not an error."""
    return await get_kg_client().get_paper_entities(arxiv_id)
