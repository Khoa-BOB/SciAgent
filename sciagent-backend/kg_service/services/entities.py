"""specs/03-kg-service-api-spec.md §2 (per-paper entities) and §5 (browse/
reverse-lookup), specs/05-kg-service-roadmap.md Sprint 3.

Needs new read-side Cypher templates alongside sciagent-KG/queries/entities.py's
existing upsert/relate templates -- entities-for-paper and papers-for-entity
lookups, parameterized by the same fixed ENTITY_LABELS/RELATION_TYPES dicts
(never a caller-supplied string built into Cypher). See
specs/02-kg-service-architecture.md §8.
"""

from neo4j import Driver

from kg_service.schemas.entities import EntityPaper, EntitySummary
from kg_service.schemas.papers import PaperEntities


def get_paper_entities(driver: Driver, arxiv_id: str) -> PaperEntities:
    raise NotImplementedError("Sprint 3 -- see specs/05-kg-service-roadmap.md")


def list_entities(driver: Driver, entity_type: str, query: str | None, limit: int) -> list[EntitySummary]:
    raise NotImplementedError("Sprint 3 -- see specs/05-kg-service-roadmap.md")


def papers_for_entity(driver: Driver, entity_type: str, normalized_name: str, limit: int) -> list[EntityPaper]:
    raise NotImplementedError("Sprint 3 -- see specs/05-kg-service-roadmap.md")
