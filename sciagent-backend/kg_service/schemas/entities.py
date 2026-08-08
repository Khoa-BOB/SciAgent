"""specs/03-kg-service-api-spec.md §5. entity_type must be one of
ENTITY_TYPES -- validated against this fixed set before it ever reaches a
Cypher query, same safety pattern as sciagent-KG/queries/entities.py's
ENTITY_LABELS dict (specs/02-kg-service-architecture.md §9).
"""

from pydantic import BaseModel

ENTITY_TYPES = ("method", "dataset", "topic")


class EntitySummary(BaseModel):
    name: str
    normalized_name: str


class EntityPaper(BaseModel):
    paper_id: str
    title: str
    confidence: float | None = None
