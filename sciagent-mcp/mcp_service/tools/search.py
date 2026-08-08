"""specs/03-mcp-tool-spec.md §3-7."""

from mcp_service.app import get_kg_client, mcp


@mcp.tool()
async def search_papers_semantic(query: str, top_k: int = 5) -> dict:
    """Search papers by natural-language meaning (semantic/vector
    similarity). Use for broad conceptual questions where the user doesn't
    name an exact technique -- e.g. 'papers about using transformers for
    protein folding'."""
    return await get_kg_client().search_semantic(query, top_k)


@mcp.tool()
async def search_papers_keyword(query: str, limit: int = 10) -> dict:
    """Search papers by exact keyword or phrase match against title and
    abstract (full-text index). Use when the user names a specific model,
    dataset, gene, or technical term verbatim."""
    return await get_kg_client().search_fulltext(query, limit)


@mcp.tool()
async def search_papers_by_author(author_name: str, limit: int = 10) -> dict:
    """Find papers by a given author name (substring match, case/accent-
    insensitive)."""
    return await get_kg_client().search_by_author(author_name, limit)


@mcp.tool()
async def search_papers_by_category(category_code: str, limit: int = 10) -> dict:
    """Find papers in a given arXiv category (exact code, e.g. 'cs.AI',
    'hep-ph')."""
    return await get_kg_client().search_by_category(category_code, limit)


@mcp.tool()
async def search_papers_by_year(start_year: int, end_year: int | None = None, limit: int = 10) -> dict:
    """Find papers first submitted within a year or year range (inclusive).
    Omit end_year to search a single year."""
    return await get_kg_client().search_by_year(start_year, end_year, limit)
