"""specs/03-kg-service-api-spec.md §6"""

from pydantic import BaseModel


class CorpusStats(BaseModel):
    paper_count: int
    author_count: int
    category_count: int
    entity_counts: dict[str, int]
    papers_with_entities: int
