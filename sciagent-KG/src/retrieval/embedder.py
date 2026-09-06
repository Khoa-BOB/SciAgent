"""Adapts the project's local SentenceTransformer model to the
neo4j_graphrag Embedder interface, so retrievers can embed query text
without depending on neo4j-graphrag's own `[sentence-transformers]` extra
-- that extra pins sentence-transformers<4.0.0, which conflicts with the
>=5.6.1 this project needs for the embeddinggemma-300m model.
"""

import os

# Skip huggingface_hub's "is my cached model still current" network round
# trips (~10 HEAD requests, ~3s) on every retrieval CLI invocation. Safe to
# default on here specifically: retrieval only ever runs after ingestion's
# embed stage or extraction's resolve stage has already downloaded this
# exact model to build the embeddings already sitting in Neo4j, so there's
# no first-download case this could break. setdefault so an operator can
# still force online checks (e.g. after bumping MODEL_NAME) by setting
# HF_HUB_OFFLINE=0 themselves. Must run before sentence_transformers is
# imported, since huggingface_hub reads this at import time.
os.environ.setdefault("HF_HUB_OFFLINE", "1")

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
