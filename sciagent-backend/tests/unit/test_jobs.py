"""Unit tests for kg_service.jobs.run_ingest_job -- the ingest worker task.

Mocks MinIO, the write-scoped Neo4j driver, and sciagent-KG's own pipeline
functions (apply_schema/load_metadata/run_embedding/run_validation), so this
runs without live Neo4j/MinIO/Redis or downloading the embedding model.
"""

from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from kg_service import jobs


@dataclass
class _FakeCheck:
    name: str


@dataclass
class _FakeCheckResult:
    check: _FakeCheck
    violations: int


def test_run_ingest_job_runs_full_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_minio = MagicMock()
    monkeypatch.setattr(jobs, "get_minio_client", lambda: fake_minio)

    fake_driver = MagicMock()
    monkeypatch.setattr(jobs, "_write_driver", lambda: fake_driver)
    monkeypatch.setattr(jobs, "_get_embedding_model", lambda: object())

    fake_apply_schema = MagicMock()
    fake_load_metadata = MagicMock(return_value=3)
    fake_run_embedding = MagicMock(return_value=3)
    fake_run_validation = MagicMock(return_value=[_FakeCheckResult(check=_FakeCheck(name="orphans"), violations=0)])

    monkeypatch.setattr("src.ingestion.schema.apply_schema", fake_apply_schema)
    monkeypatch.setattr("src.ingestion.load_metadata.load_metadata", fake_load_metadata)
    monkeypatch.setattr("src.ingestion.embeddings.index_papers.run_embedding", fake_run_embedding)
    monkeypatch.setattr("src.ingestion.validate.run_validation", fake_run_validation)

    result = jobs.run_ingest_job("ingest-uploads/job-1/papers.jsonl")

    fake_minio.fget_object.assert_called_once()
    assert fake_minio.fget_object.call_args.args[0] == jobs.MINIO_INGEST_BUCKET
    fake_apply_schema.assert_called_once_with(fake_driver)
    fake_load_metadata.assert_called_once()
    assert fake_load_metadata.call_args.kwargs["resume"] is False
    fake_run_embedding.assert_called_once()
    fake_driver.close.assert_called_once()
    assert result == {
        "loaded": 3,
        "embedded": 3,
        "validation_passed": True,
        "validation_violations": {},
    }


def test_run_ingest_job_reports_validation_violations(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jobs, "get_minio_client", lambda: MagicMock())
    fake_driver = MagicMock()
    monkeypatch.setattr(jobs, "_write_driver", lambda: fake_driver)
    monkeypatch.setattr(jobs, "_get_embedding_model", lambda: object())

    monkeypatch.setattr("src.ingestion.schema.apply_schema", MagicMock())
    monkeypatch.setattr("src.ingestion.load_metadata.load_metadata", MagicMock(return_value=1))
    monkeypatch.setattr("src.ingestion.embeddings.index_papers.run_embedding", MagicMock(return_value=1))
    monkeypatch.setattr(
        "src.ingestion.validate.run_validation",
        MagicMock(return_value=[_FakeCheckResult(check=_FakeCheck(name="orphaned_papers"), violations=2)]),
    )

    result = jobs.run_ingest_job("ingest-uploads/job-2/papers.jsonl")

    assert result["validation_passed"] is False
    assert result["validation_violations"] == {"orphaned_papers": 2}


def test_run_ingest_job_closes_driver_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jobs, "get_minio_client", lambda: MagicMock())
    fake_driver = MagicMock()
    monkeypatch.setattr(jobs, "_write_driver", lambda: fake_driver)
    monkeypatch.setattr(jobs, "_get_embedding_model", lambda: object())

    monkeypatch.setattr("src.ingestion.schema.apply_schema", MagicMock())
    monkeypatch.setattr(
        "src.ingestion.load_metadata.load_metadata", MagicMock(side_effect=RuntimeError("boom"))
    )

    with pytest.raises(RuntimeError):
        jobs.run_ingest_job("ingest-uploads/job-3/papers.jsonl")

    fake_driver.close.assert_called_once()


def test_write_driver_requires_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KG_WRITE_NEO4J_URI", raising=False)
    monkeypatch.delenv("KG_WRITE_NEO4J_USERNAME", raising=False)
    monkeypatch.delenv("KG_WRITE_NEO4J_PASSWORD", raising=False)

    with pytest.raises(EnvironmentError):
        jobs._write_driver()
