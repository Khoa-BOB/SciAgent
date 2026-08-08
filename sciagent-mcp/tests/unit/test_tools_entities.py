"""specs/03-mcp-tool-spec.md §9-10."""

from unittest.mock import AsyncMock

import pytest

from mcp_service.tools.entities import find_papers_by_entity, list_entities


@pytest.mark.asyncio
async def test_list_entities_delegates(fake_kg_client: AsyncMock) -> None:
    fake_kg_client.list_entities.return_value = {"entities": []}

    result = await list_entities("method", query="clip", limit=10)

    fake_kg_client.list_entities.assert_awaited_once_with("method", "clip", 10)
    assert result == {"entities": []}


@pytest.mark.asyncio
async def test_list_entities_defaults_query_to_none(fake_kg_client: AsyncMock) -> None:
    fake_kg_client.list_entities.return_value = {"entities": []}

    await list_entities("dataset")

    fake_kg_client.list_entities.assert_awaited_once_with("dataset", None, 20)


@pytest.mark.asyncio
async def test_find_papers_by_entity_delegates(fake_kg_client: AsyncMock) -> None:
    fake_kg_client.papers_for_entity.return_value = {"papers": []}

    result = await find_papers_by_entity("topic", "graph-neural-networks", limit=5)

    fake_kg_client.papers_for_entity.assert_awaited_once_with("topic", "graph-neural-networks", 5)
    assert result == {"papers": []}
