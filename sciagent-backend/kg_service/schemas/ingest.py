"""specs/03-kg-service-api-spec.md §8"""

from pydantic import BaseModel


class IngestJobCreated(BaseModel):
    job_id: str
    status: str
    record_count: int


class IngestJobResult(BaseModel):
    loaded: int
    embedded: int
    validation_passed: bool
    validation_violations: dict[str, int] = {}


class IngestJobStatus(BaseModel):
    job_id: str
    status: str
    result: IngestJobResult | None = None
    error: str | None = None
