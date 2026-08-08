"""specs/03-kg-service-api-spec.md §2"""

from pydantic import BaseModel


class PaperDetail(BaseModel):
    paper_id: str
    title: str
    abstract: str
    authors: list[str] = []
    categories: list[str] = []
    journal: str | None = None
    doi: str | None = None
    update_date: str | None = None
    versions: list[str] = []


class PaperEmbedding(BaseModel):
    paper_id: str
    embedding: list[float]


class EntityMention(BaseModel):
    name: str
    confidence: float | None = None


class PaperEntities(BaseModel):
    paper_id: str
    methods: list[EntityMention] = []
    datasets: list[EntityMention] = []
    topics: list[EntityMention] = []
