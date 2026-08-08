"""specs/03-kg-service-api-spec.md §1. Public -- no X-Service-Key required,
load balancers and orchestrators need to call these without a service key.
"""

from fastapi import APIRouter

from kg_service.deps import get_driver
from kg_service.errors import ApiError, ErrorCode

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@router.get("/readyz")
def readyz() -> dict:
    try:
        get_driver().execute_query("RETURN 1")
    except Exception as error:
        raise ApiError(503, ErrorCode.NEO4J_UNAVAILABLE, "Neo4j is unreachable.") from error
    return {"status": "ok", "neo4j": "reachable"}
