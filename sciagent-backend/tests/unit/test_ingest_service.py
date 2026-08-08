"""Unit tests for kg_service.services.ingest -- specs/03-kg-service-api-spec.md §8.

Mocks MinIO/RQ/Job.fetch directly, so these run without live MinIO/Redis --
same convention as tests/unit/test_search_service.py mocking the Neo4j-backed
retrieval classes.
"""

import json
from unittest.mock import MagicMock

import pytest

from kg_service.errors import ApiError, ErrorCode
from kg_service.services import ingest as ingest_service


def _jsonl(*records: dict) -> bytes:
    return "\n".join(json.dumps(record) for record in records).encode("utf-8")


def test_create_ingest_job_rejects_oversized_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ingest_service, "MAX_INGEST_FILE_BYTES", 10)

    with pytest.raises(ApiError) as exc_info:
        ingest_service.create_ingest_job("papers.jsonl", b"x" * 11)
    assert exc_info.value.code == ErrorCode.INGEST_FILE_TOO_LARGE
    assert exc_info.value.status_code == 413


def test_create_ingest_job_rejects_empty_file() -> None:
    with pytest.raises(ApiError) as exc_info:
        ingest_service.create_ingest_job("papers.jsonl", b"\n\n  \n")
    assert exc_info.value.code == ErrorCode.INGEST_FILE_EMPTY


def test_create_ingest_job_rejects_invalid_json() -> None:
    with pytest.raises(ApiError) as exc_info:
        ingest_service.create_ingest_job("papers.jsonl", b"not json\n")
    assert exc_info.value.code == ErrorCode.INGEST_FILE_INVALID_JSONL


def test_create_ingest_job_rejects_record_missing_id() -> None:
    content = _jsonl({"title": "No id field"})

    with pytest.raises(ApiError) as exc_info:
        ingest_service.create_ingest_job("papers.jsonl", content)
    assert exc_info.value.code == ErrorCode.INGEST_FILE_INVALID_JSONL


def test_create_ingest_job_stages_upload_and_enqueues(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_minio = MagicMock()
    fake_minio.bucket_exists.return_value = True
    monkeypatch.setattr(ingest_service, "get_minio_client", lambda: fake_minio)

    fake_queue = MagicMock()
    monkeypatch.setattr(ingest_service, "get_ingest_queue", lambda: fake_queue)

    content = _jsonl({"id": "2401.00001", "title": "A paper"}, {"id": "2401.00002", "title": "Another"})
    result = ingest_service.create_ingest_job("papers.jsonl", content)

    assert result.status == "queued"
    assert result.record_count == 2
    fake_minio.put_object.assert_called_once()
    fake_queue.enqueue.assert_called_once()
    assert fake_queue.enqueue.call_args.kwargs["job_id"] == result.job_id


def test_create_ingest_job_wraps_minio_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_minio = MagicMock()
    fake_minio.bucket_exists.side_effect = Exception("connection refused")
    monkeypatch.setattr(ingest_service, "get_minio_client", lambda: fake_minio)

    content = _jsonl({"id": "2401.00001"})
    with pytest.raises(ApiError) as exc_info:
        ingest_service.create_ingest_job("papers.jsonl", content)
    assert exc_info.value.code == ErrorCode.INGEST_STORAGE_UNAVAILABLE


def test_get_ingest_job_status_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    from rq.exceptions import NoSuchJobError
    from rq.job import Job

    def fake_fetch(cls, id, connection=None, serializer=None):
        raise NoSuchJobError()

    monkeypatch.setattr(Job, "fetch", classmethod(fake_fetch))
    monkeypatch.setattr("kg_service.deps.get_redis_conn", lambda: MagicMock())

    with pytest.raises(ApiError) as exc_info:
        ingest_service.get_ingest_job_status("missing-job")
    assert exc_info.value.code == ErrorCode.INGEST_JOB_NOT_FOUND
    assert exc_info.value.status_code == 404


def test_get_ingest_job_status_finished(monkeypatch: pytest.MonkeyPatch) -> None:
    from rq.job import Job

    fake_job = MagicMock()
    fake_job.get_status.return_value = "finished"
    fake_job.result = {"loaded": 2, "embedded": 2, "validation_passed": True, "validation_violations": {}}

    monkeypatch.setattr(Job, "fetch", classmethod(lambda cls, id, connection=None, serializer=None: fake_job))
    monkeypatch.setattr("kg_service.deps.get_redis_conn", lambda: MagicMock())

    status = ingest_service.get_ingest_job_status("job-1")
    assert status.status == "finished"
    assert status.result is not None
    assert status.result.loaded == 2
    assert status.error is None


def test_get_ingest_job_status_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    from rq.job import Job

    fake_job = MagicMock()
    fake_job.get_status.return_value = "failed"
    fake_job.exc_info = "Traceback (most recent call last): ..."

    monkeypatch.setattr(Job, "fetch", classmethod(lambda cls, id, connection=None, serializer=None: fake_job))
    monkeypatch.setattr("kg_service.deps.get_redis_conn", lambda: MagicMock())

    status = ingest_service.get_ingest_job_status("job-2")
    assert status.status == "failed"
    assert status.result is None
    assert status.error == fake_job.exc_info
