"""specs/03-kg-service-api-spec.md §8"""

from pydantic import BaseModel


class IngestJobCreated(BaseModel):
    job_id: str
    status: str
    record_count: int
    run_extraction: bool = False


class IngestExtractionResult(BaseModel):
    papers_extracted: int
    entities_written: int
    relationships_written: int
    error: str | None = None


class IngestJobResult(BaseModel):
    loaded: int
    embedded: int
    validation_passed: bool
    validation_violations: dict[str, int] = {}
    extraction: IngestExtractionResult | None = None


class IngestJobStatus(BaseModel):
    job_id: str
    status: str
    result: IngestJobResult | None = None
    error: str | None = None
