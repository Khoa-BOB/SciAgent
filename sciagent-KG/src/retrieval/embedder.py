"""Adapts the project's local SentenceTransformer model to the
neo4j_graphrag Embedder interface, so retrievers can embed query text
without depending on neo4j-graphrag's own `[sentence-transformers]` extra
-- that extra pins sentence-transformers<4.0.0, which conflicts with the
>=5.6.1 this project needs for the embeddinggemma-300m model.
"""

from neo4j_graphrag.embeddings.base import Embedder
from sentence_transformers import SentenceTransformer

MODEL_NAME = "google/embeddinggemma-300m"


class LocalSentenceTransformerEmbedder(Embedder):
    def __init__(self, model_name: str = MODEL_NAME) -> None:
        super().__init__()
        self.model = SentenceTransformer(model_name)

    def embed_query(self, text: str) -> list[float]:
        if not text.strip():
            raise ValueError("Query cannot be empty")

        return self.model.encode(
            text,
            normalize_embeddings=True,
            prompt_name="query",
        ).tolist()
