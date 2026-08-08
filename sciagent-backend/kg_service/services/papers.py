"""Thin adapter over sciagent-KG's retrieval classes -- specs/02-kg-service-architecture.md §1:
this module holds no Cypher of its own, it only translates between HTTP
schemas and sciagent-KG's existing dataclasses.
"""

import kg_service.kg_path  # noqa: F401  -- must run before importing sciagent-KG modules
from neo4j import Driver
from queries.search import PAPER_DETAIL

from kg_service.config import NEO4J_DATABASE
from kg_service.errors import ApiError, ErrorCode
from kg_service.schemas.papers import PaperDetail


def get_paper(driver: Driver, arxiv_id: str) -> PaperDetail:
    records, _, _ = driver.execute_query(PAPER_DETAIL, paper_id=arxiv_id, database_=NEO4J_DATABASE, routing_="r")
    if not records:
        raise ApiError(404, ErrorCode.PAPER_NOT_FOUND, f"No paper with arxiv_id '{arxiv_id}'.")

    record = records[0]
    return PaperDetail(
        paper_id=record["paper_id"],
        title=record["title"],
        abstract=record["abstract"],
        authors=record["authors"],
        categories=record["categories"],
        journal=record["journal"],
        doi=record["doi"],
        update_date=record["update_date"],
        versions=record["versions"],
    )
