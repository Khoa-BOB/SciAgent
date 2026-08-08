"""specs/03-kg-service-api-spec.md §3, specs/05-kg-service-roadmap.md Sprint 2.

Wires to sciagent-KG's src.retrieval.search.PaperSearch (fulltext/author/
category/year) and src.retrieval.vector_search.PaperVectorSearch (semantic).
Not yet implemented -- placeholders so the router layer has a stable
import target to build against.
"""

from neo4j import Driver

from kg_service.schemas.search import PaperSummary


def search_fulltext(driver: Driver, query_text: str, limit: int) -> list[PaperSummary]:
    raise NotImplementedError("Sprint 2 -- see specs/05-kg-service-roadmap.md")


def search_semantic(driver: Driver, query_text: str, top_k: int) -> list[PaperSummary]:
    raise NotImplementedError("Sprint 2 -- see specs/05-kg-service-roadmap.md")


def search_semantic_by_embedding(driver: Driver, embedding: list[float], top_k: int) -> list[PaperSummary]:
    raise NotImplementedError("Sprint 2 -- see specs/05-kg-service-roadmap.md")


def search_by_author(driver: Driver, name: str, limit: int) -> list[PaperSummary]:
    raise NotImplementedError("Sprint 2 -- see specs/05-kg-service-roadmap.md")


def search_by_category(driver: Driver, code: str, limit: int) -> list[PaperSummary]:
    raise NotImplementedError("Sprint 2 -- see specs/05-kg-service-roadmap.md")


def search_by_year(driver: Driver, start_year: int, end_year: int, limit: int) -> list[PaperSummary]:
    raise NotImplementedError("Sprint 2 -- see specs/05-kg-service-roadmap.md")
