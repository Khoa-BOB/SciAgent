"""specs/03-kg-service-api-spec.md §4"""

from fastapi import APIRouter, Depends
from neo4j import Driver

from kg_service.auth import require_service_key
from kg_service.deps import get_driver
from kg_service.errors import ApiError, ErrorCode
from kg_service.schemas.graph import GraphExpandRequest, GraphExpandResponse
from kg_service.services import graph as graph_service

router = APIRouter(prefix="/v1/graph", tags=["graph"], dependencies=[Depends(require_service_key)])

MAX_RELATED_LIMIT = 50
MAX_POOL_SIZE = 200


@router.post("/expand", response_model=GraphExpandResponse)
def expand_graph(request: GraphExpandRequest, driver: Driver = Depends(get_driver)) -> GraphExpandResponse:
    if not request.paper_ids:
        raise ApiError(400, ErrorCode.EMPTY_PAPER_IDS, "paper_ids must not be empty.")
    request.related_limit = min(request.related_limit, MAX_RELATED_LIMIT)
    request.pool_size = min(request.pool_size, MAX_POOL_SIZE)
    return graph_service.expand_graph(driver, request)
