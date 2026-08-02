import os
from dataclasses import dataclass

from dotenv import load_dotenv
from neo4j import GraphDatabase
from sentence_transformers import SentenceTransformer


MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
INDEX_NAME = "paper_embedding_index"


@dataclass
class SearchResult:
    paper_id: str
    title: str
    abstract: str
    score: float


class PaperVectorSearch:
    def __init__(self) -> None:
        load_dotenv()

        self.database = os.getenv("NEO4J_DATABASE", "neo4j")
        self.driver = GraphDatabase.driver(
            os.environ["NEO4J_URI"],
            auth=(
                os.environ["NEO4J_USERNAME"],
                os.environ["NEO4J_PASSWORD"],
            ),
        )
        self.model = SentenceTransformer(MODEL_NAME)

    def close(self) -> None:
        self.driver.close()

    def embed_query(self, query: str) -> list[float]:
        if not query.strip():
            raise ValueError("Query cannot be empty")

        return self.model.encode(
            query,
            normalize_embeddings=True,
        ).tolist()

    def search(
        self,
        query: str,
        top_k: int = 5,
    ) -> list[SearchResult]:
        return self.search_by_embedding(self.embed_query(query), top_k=top_k)

    def search_by_embedding(
        self,
        query_embedding: list[float],
        top_k: int = 5,
    ) -> list[SearchResult]:
        records, _, _ = self.driver.execute_query(
            """
            CALL db.index.vector.queryNodes(
                $index_name,
                $top_k,
                $query_embedding
            )
            YIELD node, score
            RETURN node.arxiv_id AS paper_id,
                   node.title AS title,
                   node.abstract AS abstract,
                   score
            ORDER BY score DESC
            """,
            index_name=INDEX_NAME,
            top_k=top_k,
            query_embedding=query_embedding,
            database_=self.database,
            routing_="r",
        )

        return [
            SearchResult(
                paper_id=record["paper_id"],
                title=record["title"],
                abstract=record["abstract"],
                score=record["score"],
            )
            for record in records
        ]