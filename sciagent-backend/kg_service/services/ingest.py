"""specs/03-kg-service-api-spec.md §8, specs/02-kg-service-architecture.md §8.

Validates and stages an uploaded metadata file, then hands it off to the
ingest worker (kg_service/jobs.py) via MinIO (file) + Redis/RQ (job). This
process never touches Neo4j with write intent -- it only enqueues work for a
separate worker process that holds the write-scoped credential. See
kg_service/jobs.py's docstring for the credential boundary this preserves.
"""

import json
import uuid
from io import BytesIO

from kg_service.config import MAX_INGEST_FILE_BYTES, MINIO_INGEST_BUCKET
from kg_service.deps import get_ingest_queue, get_minio_client
from kg_service.errors import ApiError, ErrorCode
from kg_service.schemas.ingest import IngestJobCreated, IngestJobResult, IngestJobStatus


def _validate_jsonl(content: bytes) -> int:
    """Reject anything the worker's src.ingestion.transform.transform() would
    crash on -- every non-blank line must be a JSON object with a non-empty
    'id' (the raw arXiv record key transform() reads as arxiv_id). Mirrors
    sciagent-KG's own load_metadata.read_metadata() error shape.
    """
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ApiError(422, ErrorCode.INGEST_FILE_INVALID_JSONL, "File is not valid UTF-8 text.") from error

    record_count = 0
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue

        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise ApiError(
                422, ErrorCode.INGEST_FILE_INVALID_JSONL, f"Invalid JSON on line {line_number}: {error.msg}."
            ) from error

        if not isinstance(record, dict) or not str(record.get("id", "")).strip():
            raise ApiError(
                422,
                ErrorCode.INGEST_FILE_INVALID_JSONL,
                f"Line {line_number} must be a JSON object with a non-empty 'id' field.",
            )

        record_count += 1

    if record_count == 0:
        raise ApiError(422, ErrorCode.INGEST_FILE_EMPTY, "Uploaded file has no records.")

    return record_count


def _ensure_bucket(minio_client) -> None:
    try:
        if not minio_client.bucket_exists(MINIO_INGEST_BUCKET):
            minio_client.make_bucket(MINIO_INGEST_BUCKET)
    except Exception as error:
        raise ApiError(
            503, ErrorCode.INGEST_STORAGE_UNAVAILABLE, "Ingest file staging (MinIO) is unreachable."
        ) from error


def create_ingest_job(filename: str, content: bytes) -> IngestJobCreated:
    if len(content) > MAX_INGEST_FILE_BYTES:
        raise ApiError(
            413,
            ErrorCode.INGEST_FILE_TOO_LARGE,
            f"File exceeds the {MAX_INGEST_FILE_BYTES} byte limit.",
        )

    record_count = _validate_jsonl(content)

    job_id = str(uuid.uuid4())
    object_key = f"ingest-uploads/{job_id}/{filename or 'papers.jsonl'}"

    minio_client = get_minio_client()
    _ensure_bucket(minio_client)
    try:
        minio_client.put_object(
            MINIO_INGEST_BUCKET, object_key, BytesIO(content), length=len(content), content_type="application/x-ndjson"
        )
    except Exception as error:
        raise ApiError(
            503, ErrorCode.INGEST_STORAGE_UNAVAILABLE, "Failed to stage upload in MinIO."
        ) from error

    try:
        from kg_service.jobs import run_ingest_job

        get_ingest_queue().enqueue(run_ingest_job, object_key, job_id=job_id, job_timeout="6h")
    except Exception as error:
        raise ApiError(
            503, ErrorCode.INGEST_QUEUE_UNAVAILABLE, "Failed to enqueue ingest job (Redis unreachable)."
        ) from error

    return IngestJobCreated(job_id=job_id, status="queued", record_count=record_count)


def get_ingest_job_status(job_id: str) -> IngestJobStatus:
    from redis.exceptions import RedisError
    from rq.exceptions import NoSuchJobError
    from rq.job import Job

    from kg_service.deps import get_redis_conn

    try:
        job = Job.fetch(job_id, connection=get_redis_conn())
    except NoSuchJobError as error:
        raise ApiError(404, ErrorCode.INGEST_JOB_NOT_FOUND, f"No ingest job '{job_id}'.") from error
    except RedisError as error:
        raise ApiError(
            503, ErrorCode.INGEST_QUEUE_UNAVAILABLE, "Ingest job queue (Redis) is unreachable."
        ) from error

    status = job.get_status(refresh=True)
    result = IngestJobResult(**job.result) if status == "finished" else None
    error_message = job.exc_info if status == "failed" else None

    return IngestJobStatus(job_id=job_id, status=status, result=result, error=error_message)
