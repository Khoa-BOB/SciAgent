"""specs/03-kg-service-api-spec.md §8. Write path -- gated by
require_write_service_key, a separate/smaller allowlist than every other
router in this service (all read-only, gated by require_service_key).
"""

from fastapi import APIRouter, Depends, Form, UploadFile

from kg_service.auth import require_write_service_key
from kg_service.schemas.ingest import IngestJobCreated, IngestJobStatus
from kg_service.services import ingest as ingest_service

router = APIRouter(prefix="/v1/ingest-jobs", tags=["ingest"], dependencies=[Depends(require_write_service_key)])


@router.post("", response_model=IngestJobCreated, status_code=202)
async def create_ingest_job(file: UploadFile, run_extraction: bool = Form(False)) -> IngestJobCreated:
    content = await file.read()
    return ingest_service.create_ingest_job(file.filename or "papers.jsonl", content, run_extraction=run_extraction)


@router.get("/{job_id}", response_model=IngestJobStatus)
def get_ingest_job(job_id: str) -> IngestJobStatus:
    return ingest_service.get_ingest_job_status(job_id)
