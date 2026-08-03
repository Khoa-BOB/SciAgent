from dataclasses import dataclass

from sentence_transformers import SentenceTransformer

from src.config import NEO4J_DATABASE, get_driver


MODEL_NAME = "google/embeddinggemma-300m"
INDEX_NAME = "paper_embedding_index"


@dataclass
class SearchResult:
    paper_id: str
    title: str
    abstract: str
    score: float


class PaperVectorSearch:
    def __init__(self) -> None:
        self.database = NEO4J_DATABASE
        self.driver = get_driver()
        self.model = SentenceTransformer(MODEL_NAME)

    def close(self) -> None:
        self.driver.close()

    def embed_query(self, query: str) -> list[float]:
        if not query.strip():
            raise ValueError("Query cannot be empty")

        return self.model.encode(
            query,
            normalize_embeddings=True,
            prompt_name="query",
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