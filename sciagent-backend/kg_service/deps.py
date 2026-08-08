"""Shared, process-wide resources -- one Neo4j driver, created at startup and
reused across every request (specs/02-kg-service-architecture.md §3: never
one driver per request, the driver already pools connections internally).

Also holds one cached instance per sciagent-KG retrieval class
(PaperSearch/PaperVectorSearch/GraphExpander), each bound to the shared
driver above instead of the driver each class's own __init__ would otherwise
create for itself. This matters most for PaperVectorSearch, whose __init__
loads the SentenceTransformer embedding model (google/embeddinggemma-300m)
-- reloading that per request would be the dominant cost of every semantic
search call, not the Neo4j query. See specs/02-kg-service-architecture.md
§3 and specs/04-kg-service-nfr-testing-deployment.md §1.
"""

from functools import lru_cache

import kg_service.kg_path  # noqa: F401  -- must run before importing sciagent-KG modules
from neo4j import Driver, GraphDatabase

from kg_service.config import NEO4J_PASSWORD, NEO4J_URI, NEO4J_USERNAME, validate_config


@lru_cache(maxsize=1)
def get_driver() -> Driver:
    validate_config()
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))


@lru_cache(maxsize=1)
def get_paper_search():
    from src.retrieval.search import PaperSearch

    search = PaperSearch()
    search.driver = get_driver()
    return search


@lru_cache(maxsize=1)
def get_vector_search():
    from src.retrieval.vector_search import PaperVectorSearch

    vector_search = PaperVectorSearch()
    vector_search.driver = get_driver()
    return vector_search


@lru_cache(maxsize=1)
def get_graph_expander():
    from src.retrieval.graph_expand import GraphExpander

    expander = GraphExpander()
    expander.driver = get_driver()
    return expander


def close_driver() -> None:
    if get_driver.cache_info().currsize:
        get_driver().close()
        get_driver.cache_clear()
    get_paper_search.cache_clear()
    get_vector_search.cache_clear()
    get_graph_expander.cache_clear()
