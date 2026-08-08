"""specs/03-mcp-tool-spec.md §1-2."""

from unittest.mock import AsyncMock

import pytest

from mcp_service.errors import KGServiceError
from mcp_service.tools.papers import get_paper, get_paper_entities


@pytest.mark.asyncio
async def test_get_paper_delegates_to_kg_client(fake_kg_client: AsyncMock) -> None:
    fake_kg_client.get_paper.return_value = {"paper_id": "2401.00001", "title": "T"}

    result = await get_paper("2401.00001")

    fake_kg_client.get_paper.assert_awaited_once_with("2401.00001")
    assert result == {"paper_id": "2401.00001", "title": "T"}


@pytest.mark.asyncio
async def test_get_paper_propagates_not_found(fake_kg_client: AsyncMock) -> None:
    fake_kg_client.get_paper.side_effect = KGServiceError(404, "PAPER_NOT_FOUND", "no such paper")

    with pytest.raises(KGServiceError) as exc_info:
        await get_paper("missing")
    assert exc_info.value.code == "PAPER_NOT_FOUND"


@pytest.mark.asyncio
async def test_get_paper_entities_delegates_to_kg_client(fake_kg_client: AsyncMock) -> None:
    fake_kg_client.get_paper_entities.return_value = {"methods": [], "datasets": [], "topics": []}

    result = await get_paper_entities("2401.00001")

    fake_kg_client.get_paper_entities.assert_awaited_once_with("2401.00001")
    assert result == {"methods": [], "datasets": [], "topics": []}
