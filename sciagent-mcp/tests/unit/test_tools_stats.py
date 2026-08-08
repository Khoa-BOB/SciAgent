"""specs/03-mcp-tool-spec.md §11."""

from unittest.mock import AsyncMock

import pytest

from mcp_service.tools.stats import get_kg_stats


@pytest.mark.asyncio
async def test_get_kg_stats_delegates(fake_kg_client: AsyncMock) -> None:
    fake_kg_client.get_stats.return_value = {"total_papers": 42}

    result = await get_kg_stats()

    fake_kg_client.get_stats.assert_awaited_once_with()
    assert result == {"total_papers": 42}
