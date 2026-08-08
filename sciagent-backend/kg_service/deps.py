"""Shared, process-wide resources -- one Neo4j driver, created at startup and
reused across every request (specs/02-kg-service-architecture.md §3: never
one driver per request, the driver already pools connections internally).
"""

from functools import lru_cache

import kg_service.kg_path  # noqa: F401  -- must run before importing sciagent-KG modules
from neo4j import Driver, GraphDatabase

from kg_service.config import NEO4J_PASSWORD, NEO4J_URI, NEO4J_USERNAME, validate_config


@lru_cache(maxsize=1)
def get_driver() -> Driver:
    validate_config()
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))


def close_driver() -> None:
    if get_driver.cache_info().currsize:
        get_driver().close()
        get_driver.cache_clear()
