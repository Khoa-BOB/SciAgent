"""specs/02-mcp-architecture.md §5 -- KGServiceClient request building and
error translation, exercised against a fake transport (no real network, no
running KG Service) via httpx.MockTransport.
"""

import httpx
import pytest

from mcp_service.errors import KGServiceError
from mcp_service.kg_client import KGServiceClient


def _client_with(handler) -> KGServiceClient:
    client = KGServiceClient(base_url="http://kg-service.test", api_key="outbound-key")
    client._client = httpx.AsyncClient(
        base_url="http://kg-service.test",
        headers={"X-Service-Key": "outbound-key"},
        transport=httpx.MockTransport(handler),
    )
    return client


@pytest.mark.asyncio
async def test_get_paper_sends_service_key_and_returns_json() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["service_key"] = request.headers.get("x-service-key")
        return httpx.Response(200, json={"paper_id": "2401.00001", "title": "T"})

    client = _client_with(handler)

    result = await client.get_paper("2401.00001")

    assert seen["path"] == "/v1/papers/2401.00001"
    assert seen["service_key"] == "outbound-key"
    assert result == {"paper_id": "2401.00001", "title": "T"}


@pytest.mark.asyncio
async def test_search_by_year_omits_none_params() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["query"] = dict(request.url.params)
        return httpx.Response(200, json={"results": []})

    client = _client_with(handler)

    await client.search_by_year(start_year=2024, end_year=None, limit=10)

    assert seen["query"] == {"start_year": "2024", "limit": "10"}
    assert "end_year" not in seen["query"]


@pytest.mark.asyncio
async def test_expand_graph_posts_json_body() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.read()
        return httpx.Response(200, json={"expanded": []})

    client = _client_with(handler)

    await client.expand_graph(["2401.00001"], None, 5, 20)

    assert b'"paper_ids":["2401.00001"]' in seen["body"]


@pytest.mark.asyncio
async def test_non_2xx_response_raises_kg_service_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": {"code": "PAPER_NOT_FOUND", "message": "gone"}})

    client = _client_with(handler)

    with pytest.raises(KGServiceError) as exc_info:
        await client.get_paper("missing")
    assert exc_info.value.code == "PAPER_NOT_FOUND"


@pytest.mark.asyncio
async def test_connection_failure_raises_kg_service_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    client = _client_with(handler)

    with pytest.raises(KGServiceError) as exc_info:
        await client.get_stats()
    assert exc_info.value.status_code == 503
