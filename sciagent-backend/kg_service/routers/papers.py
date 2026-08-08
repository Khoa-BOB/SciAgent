"""specs/03-kg-service-api-spec.md §2, §7"""

from fastapi import APIRouter, Depends
from neo4j import Driver

from kg_service.auth import require_service_key
from kg_service.deps import get_driver
from kg_service.schemas.papers import PaperDetail, PaperEmbedding, PaperEntities
from kg_service.services import entities as entities_service
from kg_service.services import papers as papers_service

router = APIRouter(prefix="/v1/papers", tags=["papers"], dependencies=[Depends(require_service_key)])


@router.get("/{arxiv_id}", response_model=PaperDetail)
def get_paper(arxiv_id: str, driver: Driver = Depends(get_driver)) -> PaperDetail:
    return papers_service.get_paper(driver, arxiv_id)


@router.get("/{arxiv_id}/entities", response_model=PaperEntities)
def get_paper_entities(arxiv_id: str, driver: Driver = Depends(get_driver)) -> PaperEntities:
    return entities_service.get_paper_entities(driver, arxiv_id)


@router.get("/{arxiv_id}/embedding", response_model=PaperEmbedding)
def get_paper_embedding(arxiv_id: str, driver: Driver = Depends(get_driver)) -> PaperEmbedding:
    raise NotImplementedError("Sprint 1 -- see specs/05-kg-service-roadmap.md")
