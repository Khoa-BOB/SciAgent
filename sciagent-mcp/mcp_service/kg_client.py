"""Async HTTP client for the KG Service -- specs/02-mcp-architecture.md §5.

One shared instance per process (see mcp_service/app.py's lifespan), never
one per tool call -- matches sciagent-backend's "one driver per process"
rule. This is the *only* outbound dependency this service has: no Cypher,
no Neo4j driver, no sciagent-KG import anywhere in this codebase.
"""

from typing import Any

import httpx

from mcp_service.errors import error_from_exception, error_from_response


def _params(**kwargs: Any) -> dict[str, Any]:
    return {key: value for key, value in kwargs.items() if value is not None}


class KGServiceClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 10.0) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"X-Service-Key": api_key},
            timeout=timeout,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict:
        try:
            response = await self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise error_from_exception(exc) from exc
        if response.status_code < 300:
            return response.json()
        raise error_from_response(response)

    # -- §1-2 papers -----------------------------------------------------
    async def get_paper(self, arxiv_id: str) -> dict:
        return await self._request("GET", f"/v1/papers/{arxiv_id}")

    async def get_paper_entities(self, arxiv_id: str) -> dict:
        return await self._request("GET", f"/v1/papers/{arxiv_id}/entities")

    # -- §3 search ---------------------------------------------------------
    async def search_semantic(self, query: str, top_k: int) -> dict:
        return await self._request("GET", "/v1/search/semantic", params={"q": query, "top_k": top_k})

    async def search_fulltext(self, query: str, limit: int) -> dict:
        return await self._request("GET", "/v1/search/fulltext", params={"q": query, "limit": limit})

    async def search_by_author(self, name: str, limit: int) -> dict:
        return await self._request("GET", "/v1/search/by-author", params={"name": name, "limit": limit})

    async def search_by_category(self, code: str, limit: int) -> dict:
        return await self._request("GET", "/v1/search/by-category", params={"code": code, "limit": limit})

    async def search_by_year(self, start_year: int, end_year: int | None, limit: int) -> dict:
        return await self._request(
            "GET",
            "/v1/search/by-year",
            params=_params(start_year=start_year, end_year=end_year, limit=limit),
        )

    # -- §4 graph expansion --------------------------------------------------
    async def expand_graph(
        self,
        paper_ids: list[str],
        query_embedding: list[float] | None,
        related_limit: int,
        pool_size: int,
    ) -> dict:
        return await self._request(
            "POST",
            "/v1/graph/expand",
            json={
                "paper_ids": paper_ids,
                "query_embedding": query_embedding,
                "related_limit": related_limit,
                "pool_size": pool_size,
            },
        )

    # -- §5 domain entities -----------------------------------------------
    async def list_entities(self, entity_type: str, query: str | None, limit: int) -> dict:
        return await self._request(
            "GET", f"/v1/entities/{entity_type}", params=_params(q=query, limit=limit)
        )

    async def papers_for_entity(self, entity_type: str, normalized_name: str, limit: int) -> dict:
        return await self._request(
            "GET", f"/v1/entities/{entity_type}/{normalized_name}/papers", params={"limit": limit}
        )

    # -- §6 stats -----------------------------------------------------------
    async def get_stats(self) -> dict:
        return await self._request("GET", "/v1/stats")
