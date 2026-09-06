"""Combined vector + fulltext search over papers, additive alongside the
pure vector search in vector_search.py and the pure fulltext search in
queries/search.py -- neither of those alone captures both a semantically
close paper and one that just happens to share exact keywords the query
used.
"""

from dataclasses import dataclass

import neo4j
from neo4j_graphrag.retrievers import HybridRetriever
from neo4j_graphrag.types import RetrieverResultItem

from src.config import NEO4J_DATABASE, get_driver
from src.retrieval.embedder import LocalSentenceTransformerEmbedder

VECTOR_INDEX_NAME = "paper_embedding_index"
FULLTEXT_INDEX_NAME = "paper_text"


@dataclass
class HybridSearchResult:
    paper_id: str
    title: str
    abstract: str
    score: float


def _format_paper(record: neo4j.Record) -> RetrieverResultItem:
    node = record["node"]
    return RetrieverResultItem(
        content=node.get("title"),
        metadata={
            "paper_id": node.get("arxiv_id"),
            "title": node.get("title"),
            "abstract": node.get("abstract"),
            "score": record["score"],
        },
    )


class PaperHybridSearch:
    def __init__(self) -> None:
        self.database = NEO4J_DATABASE
        self.driver = get_driver()
        self.embedder = LocalSentenceTransformerEmbedder()
        self.retriever = HybridRetriever(
            driver=self.driver,
            vector_index_name=VECTOR_INDEX_NAME,
            fulltext_index_name=FULLTEXT_INDEX_NAME,
            embedder=self.embedder,
            result_formatter=_format_paper,
            neo4j_database=self.database,
        )

    def close(self) -> None:
        self.driver.close()

    def search(self, query: str, top_k: int = 5) -> list[HybridSearchResult]:
        result = self.retriever.search(query_text=query, top_k=top_k)
        return [HybridSearchResult(**item.metadata) for item in result.items]
