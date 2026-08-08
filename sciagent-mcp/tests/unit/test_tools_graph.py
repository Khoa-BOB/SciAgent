"""specs/03-mcp-tool-spec.md §8."""

from unittest.mock import AsyncMock

import pytest

from mcp_service.tools.graph import expand_paper_neighbors


@pytest.mark.asyncio
async def test_expand_paper_neighbors_delegates_and_never_passes_embedding(fake_kg_client: AsyncMock) -> None:
    fake_kg_client.expand_graph.return_value = {"papers": []}

    result = await expand_paper_neighbors(["2401.00001", "2401.00002"], related_limit=3, pool_size=15)

    fake_kg_client.expand_graph.assert_awaited_once_with(["2401.00001", "2401.00002"], None, 3, 15)
    assert result == {"papers": []}


@pytest.mark.asyncio
async def test_expand_paper_neighbors_uses_defaults(fake_kg_client: AsyncMock) -> None:
    fake_kg_client.expand_graph.return_value = {"papers": []}

    await expand_paper_neighbors(["2401.00001"])

    fake_kg_client.expand_graph.assert_awaited_once_with(["2401.00001"], None, 5, 20)
