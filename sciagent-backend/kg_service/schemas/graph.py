"""specs/03-kg-service-api-spec.md §4"""

from pydantic import BaseModel


class GraphExpandRequest(BaseModel):
    paper_ids: list[str]
    query_embedding: list[float] | None = None
    related_limit: int = 5
    pool_size: int = 20


class PaperContext(BaseModel):
    authors: list[str] = []
    categories: list[str] = []
    journal: str | None = None


class RelatedPaper(BaseModel):
    paper_id: str
    title: str
    shared_authors: list[str] = []
    shared_categories: list[str] = []
    similarity_to_query: float = 0.0


class GraphExpandResponse(BaseModel):
    seed_context: dict[str, PaperContext]
    related_papers: list[RelatedPaper]
