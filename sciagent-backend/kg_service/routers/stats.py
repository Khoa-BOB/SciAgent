"""specs/03-kg-service-api-spec.md §6"""

from fastapi import APIRouter, Depends
from neo4j import Driver

from kg_service.auth import require_service_key
from kg_service.deps import get_driver
from kg_service.schemas.stats import CorpusStats
from kg_service.services import stats as stats_service

router = APIRouter(prefix="/v1/stats", tags=["stats"], dependencies=[Depends(require_service_key)])


@router.get("", response_model=CorpusStats)
def get_corpus_stats(driver: Driver = Depends(get_driver)) -> CorpusStats:
    return stats_service.get_corpus_stats(driver)
