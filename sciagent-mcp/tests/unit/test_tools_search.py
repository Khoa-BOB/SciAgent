"""specs/03-mcp-tool-spec.md §3-7."""

from unittest.mock import AsyncMock

import pytest

from mcp_service.tools.search import (
    search_papers_by_author,
    search_papers_by_category,
    search_papers_by_year,
    search_papers_keyword,
    search_papers_semantic,
)


@pytest.mark.asyncio
async def test_search_papers_semantic_delegates(fake_kg_client: AsyncMock) -> None:
    fake_kg_client.search_semantic.return_value = {"results": []}

    result = await search_papers_semantic("transformers for protein folding", top_k=3)

    fake_kg_client.search_semantic.assert_awaited_once_with("transformers for protein folding", 3)
    assert result == {"results": []}


@pytest.mark.asyncio
async def test_search_papers_keyword_delegates(fake_kg_client: AsyncMock) -> None:
    fake_kg_client.search_fulltext.return_value = {"results": []}

    await search_papers_keyword("CLIP", limit=5)

    fake_kg_client.search_fulltext.assert_awaited_once_with("CLIP", 5)


@pytest.mark.asyncio
async def test_search_papers_by_author_delegates(fake_kg_client: AsyncMock) -> None:
    fake_kg_client.search_by_author.return_value = {"results": []}

    await search_papers_by_author("Jane Doe", limit=10)

    fake_kg_client.search_by_author.assert_awaited_once_with("Jane Doe", 10)


@pytest.mark.asyncio
async def test_search_papers_by_category_delegates(fake_kg_client: AsyncMock) -> None:
    fake_kg_client.search_by_category.return_value = {"results": []}

    await search_papers_by_category("cs.AI", limit=10)

    fake_kg_client.search_by_category.assert_awaited_once_with("cs.AI", 10)


@pytest.mark.asyncio
async def test_search_papers_by_year_delegates_with_end_year(fake_kg_client: AsyncMock) -> None:
    fake_kg_client.search_by_year.return_value = {"results": []}

    await search_papers_by_year(2020, end_year=2024, limit=10)

    fake_kg_client.search_by_year.assert_awaited_once_with(2020, 2024, 10)


@pytest.mark.asyncio
async def test_search_papers_by_year_defaults_end_year_to_none(fake_kg_client: AsyncMock) -> None:
    fake_kg_client.search_by_year.return_value = {"results": []}

    await search_papers_by_year(2024)

    fake_kg_client.search_by_year.assert_awaited_once_with(2024, None, 10)
