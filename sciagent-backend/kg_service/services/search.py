"""specs/03-kg-service-api-spec.md §3, specs/05-kg-service-roadmap.md Sprint 2.

Wires to sciagent-KG's src.retrieval.search.PaperSearch (fulltext/author/
category/year) and src.retrieval.vector_search.PaperVectorSearch (semantic),
via the process-wide cached instances in kg_service.deps (bound once to the
shared driver -- PaperVectorSearch in particular keeps its embedding model
warm across requests, see kg_service/deps.py).
"""

import kg_service.kg_path  # noqa: F401  -- must run before importing sciagent-KG modules
from neo4j import Driver
from queries.search import CATEGORY_EXISTS

from kg_service.config import NEO4J_DATABASE
from kg_service.deps import get_paper_search, get_vector_search
from kg_service.errors import ApiError, ErrorCode
from kg_service.schemas.search import PaperSummary

EMBEDDING_DIMENSIONS = 768  # paper_embedding_index, sciagent-KG/cypher/index.cypher


def _to_summary(item) -> PaperSummary:
    return PaperSummary(
        paper_id=item.paper_id,
        title=item.title,
        abstract=item.abstract,
        score=getattr(item, "score", None),
        matched_by=getattr(item, "matched_by", None),
    )


def search_fulltext(driver: Driver, query_text: str, limit: int) -> list[PaperSummary]:
    results = get_paper_search().search_fulltext(query_text, limit=limit)
    return [_to_summary(r) for r in results]


def search_semantic(driver: Driver, query_text: str, top_k: int) -> list[PaperSummary]:
    results = get_vector_search().search(query_text, top_k=top_k)
    return [_to_summary(r) for r in results]


def search_semantic_by_embedding(driver: Driver, embedding: list[float], top_k: int) -> list[PaperSummary]:
    if len(embedding) != EMBEDDING_DIMENSIONS:
        raise ApiError(
            422,
            ErrorCode.INVALID_EMBEDDING_DIMENSION,
            f"embedding must have {EMBEDDING_DIMENSIONS} dimensions, got {len(embedding)}.",
        )
    results = get_vector_search().search_by_embedding(embedding, top_k=top_k)
    return [_to_summary(r) for r in results]


def search_by_author(driver: Driver, name: str, limit: int) -> list[PaperSummary]:
    results = get_paper_search().search_by_author(name, limit=limit)
    return [_to_summary(r) for r in results]


def search_by_category(driver: Driver, code: str, limit: int) -> list[PaperSummary]:
    records, _, _ = driver.execute_query(
        CATEGORY_EXISTS, category_code=code, database_=NEO4J_DATABASE, routing_="r"
    )
    if not records:
        raise ApiError(404, ErrorCode.CATEGORY_NOT_FOUND, f"No category with code '{code}'.")
    results = get_paper_search().search_by_category(code, limit=limit)
    return [_to_summary(r) for r in results]


def search_by_year(driver: Driver, start_year: int, end_year: int, limit: int) -> list[PaperSummary]:
    results = get_paper_search().search_by_year(start_year, end_year=end_year, limit=limit)
    return [_to_summary(r) for r in results]
