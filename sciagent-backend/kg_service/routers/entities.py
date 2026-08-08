"""specs/03-kg-service-api-spec.md §5"""

from fastapi import APIRouter, Depends, Query
from neo4j import Driver

from kg_service.auth import require_service_key
from kg_service.deps import get_driver
from kg_service.errors import ApiError, ErrorCode
from kg_service.schemas.common import ListResponse
from kg_service.schemas.entities import ENTITY_TYPES, EntityPaper, EntitySummary
from kg_service.services import entities as entities_service

router = APIRouter(prefix="/v1/entities", tags=["entities"], dependencies=[Depends(require_service_key)])


def _require_known_type(entity_type: str) -> None:
    if entity_type not in ENTITY_TYPES:
        raise ApiError(
            400, ErrorCode.UNKNOWN_ENTITY_TYPE, f"entity_type must be one of {ENTITY_TYPES}, got '{entity_type}'."
        )


@router.get("/{entity_type}", response_model=ListResponse[EntitySummary])
def list_entities(
    entity_type: str,
    q: str | None = None,
    limit: int = Query(default=20, le=200),
    driver: Driver = Depends(get_driver),
) -> ListResponse:
    _require_known_type(entity_type)
    items = entities_service.list_entities(driver, entity_type, q, limit)
    return ListResponse(items=items, count=len(items))


@router.get("/{entity_type}/{normalized_name}/papers", response_model=ListResponse[EntityPaper])
def papers_for_entity(
    entity_type: str,
    normalized_name: str,
    limit: int = Query(default=20, le=200),
    driver: Driver = Depends(get_driver),
) -> ListResponse:
    _require_known_type(entity_type)
    items = entities_service.papers_for_entity(driver, entity_type, normalized_name, limit)
    return ListResponse(items=items, count=len(items))
