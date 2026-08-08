"""Thin adapter over sciagent-KG's retrieval classes -- specs/02-kg-service-architecture.md §1:
this module holds no Cypher of its own, it only translates between HTTP
schemas and sciagent-KG's existing dataclasses.
"""

import kg_service.kg_path  # noqa: F401  -- must run before importing sciagent-KG modules
from neo4j import Driver
from src.retrieval.search import PaperSearch

from kg_service.errors import ApiError, ErrorCode
from kg_service.schemas.papers import PaperDetail


def get_paper(driver: Driver, arxiv_id: str) -> PaperDetail:
    search = PaperSearch()
    search.driver = driver  # reuse the shared process-wide driver, not a new one
    details = search.get_by_id(arxiv_id)
    if details is None:
        raise ApiError(404, ErrorCode.PAPER_NOT_FOUND, f"No paper with arxiv_id '{arxiv_id}'.")

    # PAPER_BY_ID (queries/search.py) only returns paper_id/title/abstract/embedding.
    # authors/categories/journal/doi/update_date/versions need a richer query --
    # not yet added (see specs/02-kg-service-architecture.md §8's list of
    # additive changes, which should grow to include this). Left empty rather
    # than guessed at, so callers don't mistake "not wired yet" for "no authors".
    return PaperDetail(
        paper_id=details.paper_id,
        title=details.title,
        abstract=details.abstract,
    )
