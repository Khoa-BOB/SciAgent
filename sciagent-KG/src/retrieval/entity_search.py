from dataclasses import dataclass

import neo4j
from neo4j_graphrag.retrievers import VectorRetriever
from neo4j_graphrag.types import RetrieverResultItem

from src.config import NEO4J_DATABASE, get_driver
from src.retrieval.embedder import LocalSentenceTransformerEmbedder

# Fixed, hardcoded label -> vector-index-name map (never taken from request
# text) -- one VectorRetriever per label because a Neo4j vector index is
# defined against a single label.
INDEX_NAMES: dict[str, str] = {
    "Method": "method_embedding_index",
    "Dataset": "dataset_embedding_index",
    "ResearchTopic": "topic_embedding_index",
}


@dataclass
class EntitySearchResult:
    entity_type: str
    normalized_name: str
    name: str
    score: float


def _make_formatter(entity_type: str):
    def _format(record: neo4j.Record) -> RetrieverResultItem:
        node = record["node"]
        return RetrieverResultItem(
            content=node.get("name"),
            metadata={
                "entity_type": entity_type,
                "normalized_name": node.get("normalized_name"),
                "name": node.get("name"),
                "score": record["score"],
            },
        )

    return _format


class EntitySearch:
    def __init__(self) -> None:
        self.database = NEO4J_DATABASE
        self.driver = get_driver()
        self.embedder = LocalSentenceTransformerEmbedder()
        self.retrievers: dict[str, VectorRetriever] = {
            entity_type: VectorRetriever(
                driver=self.driver,
                index_name=index_name,
                embedder=self.embedder,
                result_formatter=_make_formatter(entity_type),
                neo4j_database=self.database,
            )
            for entity_type, index_name in INDEX_NAMES.items()
        }

    def close(self) -> None:
        self.driver.close()

    def embed_query(self, query: str) -> list[float]:
        return self.embedder.embed_query(query)

    def search(
        self,
        query: str,
        top_k: int = 5,
        entity_types: list[str] | None = None,
    ) -> list[EntitySearchResult]:
        return self.search_by_embedding(
            self.embed_query(query), top_k=top_k, entity_types=entity_types
        )

    def search_by_embedding(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        entity_types: list[str] | None = None,
    ) -> list[EntitySearchResult]:
        """Vector-search each requested entity label's index independently
        (Neo4j has no cross-label vector index) and merge by score.
        `entity_types` must be a subset of INDEX_NAMES's keys; defaults to
        searching all three."""
        types = entity_types if entity_types is not None else list(INDEX_NAMES)

        results: list[EntitySearchResult] = []
        for entity_type in types:
            result = self.retrievers[entity_type].search(
                query_vector=query_embedding, top_k=top_k
            )
            results.extend(
                EntitySearchResult(**item.metadata) for item in result.items
            )

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]
