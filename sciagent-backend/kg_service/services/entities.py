"""specs/03-kg-service-api-spec.md §2 (per-paper entities) and §5 (browse/
reverse-lookup), specs/05-kg-service-roadmap.md Sprint 3.

Wired to the new read-side Cypher templates in sciagent-KG's
queries/entities.py -- entities-for-paper, list-entities, and
papers-for-entity, parameterized by the same fixed ENTITY_LABELS/
RELATION_TYPES dicts the upsert templates already use (never a
caller-supplied string built into Cypher). See
specs/02-kg-service-architecture.md §9.
"""

import kg_service.kg_path  # noqa: F401  -- must run before importing sciagent-KG modules
from neo4j import Driver
from queries.entities import (
    ENTITIES_FOR_PAPER,
    entity_exists_query,
    list_entities_query,
    papers_for_entity_query,
)

from kg_service.config import NEO4J_DATABASE
from kg_service.errors import ApiError, ErrorCode
from kg_service.schemas.entities import EntityPaper, EntitySummary
from kg_service.schemas.papers import EntityMention, PaperEntities


def get_paper_entities(driver: Driver, arxiv_id: str) -> PaperEntities:
    records, _, _ = driver.execute_query(
        ENTITIES_FOR_PAPER, paper_id=arxiv_id, database_=NEO4J_DATABASE, routing_="r"
    )
    if not records:
        raise ApiError(404, ErrorCode.PAPER_NOT_FOUND, f"No paper with arxiv_id '{arxiv_id}'.")

    record = records[0]
    return PaperEntities(
        paper_id=record["paper_id"],
        methods=[EntityMention(name=m["name"], confidence=m["confidence"]) for m in record["methods"]],
        datasets=[EntityMention(name=d["name"], confidence=d["confidence"]) for d in record["datasets"]],
        topics=[EntityMention(name=t["name"], confidence=t["confidence"]) for t in record["topics"]],
    )


def list_entities(driver: Driver, entity_type: str, query: str | None, limit: int) -> list[EntitySummary]:
    records, _, _ = driver.execute_query(
        list_entities_query(entity_type), query=query, limit=limit, database_=NEO4J_DATABASE, routing_="r"
    )
    return [EntitySummary(name=r["name"], normalized_name=r["normalized_name"]) for r in records]


def papers_for_entity(driver: Driver, entity_type: str, normalized_name: str, limit: int) -> list[EntityPaper]:
    exists, _, _ = driver.execute_query(
        entity_exists_query(entity_type),
        normalized_name=normalized_name,
        database_=NEO4J_DATABASE,
        routing_="r",
    )
    if not exists:
        raise ApiError(
            404, ErrorCode.ENTITY_NOT_FOUND, f"No {entity_type} with normalized_name '{normalized_name}'."
        )

    records, _, _ = driver.execute_query(
        papers_for_entity_query(entity_type),
        normalized_name=normalized_name,
        limit=limit,
        database_=NEO4J_DATABASE,
        routing_="r",
    )
    return [EntityPaper(paper_id=r["paper_id"], title=r["title"], confidence=r["confidence"]) for r in records]
