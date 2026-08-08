"""specs/03-kg-service-api-spec.md §6, specs/05-kg-service-roadmap.md Sprint 3.

Wired to the new corpus-stats query in sciagent-KG's queries/stats.py --
see specs/02-kg-service-architecture.md §9.
"""

import kg_service.kg_path  # noqa: F401  -- must run before importing sciagent-KG modules
from neo4j import Driver
from queries.stats import CORPUS_STATS

from kg_service.config import NEO4J_DATABASE
from kg_service.schemas.stats import CorpusStats


def get_corpus_stats(driver: Driver) -> CorpusStats:
    records, _, _ = driver.execute_query(CORPUS_STATS, database_=NEO4J_DATABASE, routing_="r")
    record = records[0]
    return CorpusStats(
        paper_count=record["paper_count"],
        author_count=record["author_count"],
        category_count=record["category_count"],
        entity_counts={
            "method": record["method_count"],
            "dataset": record["dataset_count"],
            "topic": record["topic_count"],
        },
        papers_with_entities=record["papers_with_entities"],
    )
