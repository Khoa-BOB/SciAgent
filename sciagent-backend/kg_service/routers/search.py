"""specs/03-kg-service-api-spec.md §3"""

from fastapi import APIRouter, Depends, Query
from neo4j import Driver

from kg_service.auth import require_service_key
from kg_service.deps import get_driver
from kg_service.errors import ApiError, ErrorCode
from kg_service.schemas.common import ListResponse
from kg_service.schemas.search import EmbeddingSearchRequest, PaperSummary
from kg_service.services import search as search_service

router = APIRouter(prefix="/v1/search", tags=["search"], dependencies=[Depends(require_service_key)])


def _require_non_empty(q: str) -> None:
    if not q.strip():
        raise ApiError(400, ErrorCode.EMPTY_QUERY, "Query text must not be empty.")


@router.get("/fulltext", response_model=ListResponse[PaperSummary])
def search_fulltext(
    q: str, limit: int = Query(default=10, le=100), driver: Driver = Depends(get_driver)
) -> ListResponse:
    _require_non_empty(q)
    items = search_service.search_fulltext(driver, q, limit)
    return ListResponse(items=items, count=len(items))


@router.get("/semantic", response_model=ListResponse[PaperSummary])
def search_semantic(
    q: str, top_k: int = Query(default=5, le=50), driver: Driver = Depends(get_driver)
) -> ListResponse:
    _require_non_empty(q)
    items = search_service.search_semantic(driver, q, top_k)
    return ListResponse(items=items, count=len(items))


@router.post("/semantic/by-embedding", response_model=ListResponse[PaperSummary])
def search_semantic_by_embedding(
    request: EmbeddingSearchRequest, driver: Driver = Depends(get_driver)
) -> ListResponse:
    items = search_service.search_semantic_by_embedding(driver, request.embedding, request.top_k)
    return ListResponse(items=items, count=len(items))


@router.get("/by-author", response_model=ListResponse[PaperSummary])
def search_by_author(
    name: str, limit: int = Query(default=10, le=100), driver: Driver = Depends(get_driver)
) -> ListResponse:
    items = search_service.search_by_author(driver, name, limit)
    return ListResponse(items=items, count=len(items))


@router.get("/by-category", response_model=ListResponse[PaperSummary])
def search_by_category(
    code: str, limit: int = Query(default=10, le=100), driver: Driver = Depends(get_driver)
) -> ListResponse:
    items = search_service.search_by_category(driver, code, limit)
    return ListResponse(items=items, count=len(items))


@router.get("/by-year", response_model=ListResponse[PaperSummary])
def search_by_year(
    start_year: int,
    end_year: int | None = None,
    limit: int = Query(default=10, le=100),
    driver: Driver = Depends(get_driver),
) -> ListResponse:
    resolved_end_year = end_year if end_year is not None else start_year
    if resolved_end_year < start_year:
        raise ApiError(400, ErrorCode.INVALID_YEAR_RANGE, "end_year must be >= start_year.")
    items = search_service.search_by_year(driver, start_year, resolved_end_year, limit)
    return ListResponse(items=items, count=len(items))
