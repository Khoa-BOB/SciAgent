"""specs/03-kg-service-api-spec.md §6, specs/05-kg-service-roadmap.md Sprint 3.

Needs a new (small, additive) corpus-stats query -- see
specs/02-kg-service-architecture.md §8.
"""

from neo4j import Driver

from kg_service.schemas.stats import CorpusStats


def get_corpus_stats(driver: Driver) -> CorpusStats:
    raise NotImplementedError("Sprint 3 -- see specs/05-kg-service-roadmap.md")
