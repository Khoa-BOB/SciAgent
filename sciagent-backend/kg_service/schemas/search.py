"""specs/03-kg-service-api-spec.md §3"""

from pydantic import BaseModel


class PaperSummary(BaseModel):
    paper_id: str
    title: str
    abstract: str
    score: float | None = None
    matched_by: str | None = None


class EmbeddingSearchRequest(BaseModel):
    embedding: list[float]
    top_k: int = 5
