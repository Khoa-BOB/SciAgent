"""Unit tests for kg_service.jobs.run_ingest_job -- the ingest worker task.

Mocks MinIO, the write-scoped Neo4j driver, and sciagent-KG's own pipeline
functions (apply_schema/load_metadata/run_embedding/run_validation), so this
runs without live Neo4j/MinIO/Redis or downloading the embedding model.
"""

import json
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


# --- Extraction follow-up (run_extraction=True) -----------------------------


def test_build_extraction_shard_filters_incomplete_records(tmp_path) -> None:
    upload_path = tmp_path / "upload.jsonl"
    upload_path.write_text(
        "\n".join(
            [
                json.dumps({"id": "2401.00001", "title": "T1", "abstract": "A1"}),
                json.dumps({"id": "2401.00002", "title": "", "abstract": "A2"}),  # blank title -> excluded
                json.dumps({"id": "", "title": "T3", "abstract": "A3"}),  # blank id -> excluded
                "",
            ]
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "shard.jsonl"

    arxiv_ids = jobs._build_extraction_shard(upload_path, output_path)

    assert arxiv_ids == ["2401.00001"]
    lines = output_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == {"arxiv_id": "2401.00001", "title": "T1", "abstract": "A1"}


def test_run_extraction_followup_skips_when_no_eligible_papers(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr("src.extraction.export.DEFAULT_OUTPUT_DIR", tmp_path / "shards")

    upload_path = tmp_path / "upload.jsonl"
    upload_path.write_text(json.dumps({"id": "2401.00001", "title": "", "abstract": ""}) + "\n", encoding="utf-8")

    result = jobs._run_extraction_followup(upload_path, MagicMock())

    assert result == {"papers_extracted": 0, "entities_written": 0, "relationships_written": 0}


def test_run_extraction_followup_seeds_resolve_from_neo4j_and_scopes_to_job_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    shards_dir = tmp_path / "shards"
    monkeypatch.setattr("src.extraction.export.DEFAULT_OUTPUT_DIR", shards_dir)
    monkeypatch.setattr(jobs, "_get_extraction_client", lambda: MagicMock())
    monkeypatch.setattr(jobs, "_get_embedding_model", lambda: object())
    monkeypatch.setattr("src.extraction.extract.run_extraction", MagicMock(return_value=2))

    # fetch_existing_clusters() stands in for a Neo4j read of every canonical
    # entity that already has a stored embedding -- the whole point of the
    # incremental design (specs/02-kg-service-architecture.md §8.5) is that
    # resolve() gets seeded with this instead of re-reading the whole corpus.
    existing_clusters = {"method": [("graph neural network", "fake-embedding")], "dataset": [], "topic": []}
    fake_fetch = MagicMock(return_value=existing_clusters)
    monkeypatch.setattr("src.extraction.merge.fetch_existing_clusters", fake_fetch)

    resolved_rows = [
        {"paper_id": "2401.00001", "entity_type": "method", "name": "graph neural network", "normalized_name": "graph neural network", "raw_name": "GNN"},
        {"paper_id": "2401.00002", "entity_type": "method", "name": "graph neural network", "normalized_name": "graph neural network", "raw_name": "graph neural network"},
    ]
    new_embeddings = {"method": {}}
    fake_resolve = MagicMock(return_value=(resolved_rows, new_embeddings))
    monkeypatch.setattr("src.extraction.resolve.resolve", fake_resolve)

    fake_merge = MagicMock(return_value=(1, 2))
    monkeypatch.setattr("src.extraction.merge.merge_resolved", fake_merge)

    upload_path = tmp_path / "upload.jsonl"
    upload_path.write_text(
        "\n".join(
            [
                json.dumps({"id": "2401.00001", "title": "T1", "abstract": "A1"}),
                json.dumps({"id": "2401.00002", "title": "T2", "abstract": "A2"}),
            ]
        ),
        encoding="utf-8",
    )

    driver = MagicMock()
    result = jobs._run_extraction_followup(upload_path, driver)

    assert result == {"papers_extracted": 2, "entities_written": 1, "relationships_written": 2}

    fake_fetch.assert_called_once()
    assert fake_fetch.call_args.args[0] is driver

    fake_resolve.assert_called_once()
    resolved_shard_dir = fake_resolve.call_args.args[0]
    # A job-scoped subdirectory under the shards tree, NOT the flat shards_dir
    # itself -- resolve() globs every *.extracted.jsonl in whatever directory
    # it's given, so scoping to just this job's own new shard is what keeps
    # this job from re-processing the whole historical corpus.
    assert resolved_shard_dir != shards_dir
    assert resolved_shard_dir.parent.name == "ingest-jobs"
    assert resolved_shard_dir.parent.parent == shards_dir
    assert fake_resolve.call_args.kwargs["existing_clusters"] is existing_clusters

    fake_merge.assert_called_once()
    assert fake_merge.call_args.args[0] is driver
    assert fake_merge.call_args.args[2] == resolved_rows
    assert fake_merge.call_args.kwargs["new_embeddings"] is new_embeddings


def test_run_ingest_job_with_extraction_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jobs, "get_minio_client", lambda: MagicMock())
    fake_driver = MagicMock()
    monkeypatch.setattr(jobs, "_write_driver", lambda: fake_driver)
    monkeypatch.setattr(jobs, "_get_embedding_model", lambda: object())
    monkeypatch.setattr("src.ingestion.schema.apply_schema", MagicMock())
    monkeypatch.setattr("src.ingestion.load_metadata.load_metadata", MagicMock(return_value=1))
    monkeypatch.setattr("src.ingestion.embeddings.index_papers.run_embedding", MagicMock(return_value=1))
    monkeypatch.setattr("src.ingestion.validate.run_validation", MagicMock(return_value=[]))

    fake_followup = MagicMock(
        return_value={"papers_extracted": 1, "entities_written": 2, "relationships_written": 2}
    )
    monkeypatch.setattr(jobs, "_run_extraction_followup", fake_followup)

    result = jobs.run_ingest_job("ingest-uploads/job-4/papers.jsonl", run_extraction=True)

    fake_followup.assert_called_once()
    assert result["extraction"] == {"papers_extracted": 1, "entities_written": 2, "relationships_written": 2}


def test_run_ingest_job_extraction_failure_does_not_fail_the_job(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jobs, "get_minio_client", lambda: MagicMock())
    fake_driver = MagicMock()
    monkeypatch.setattr(jobs, "_write_driver", lambda: fake_driver)
    monkeypatch.setattr(jobs, "_get_embedding_model", lambda: object())
    monkeypatch.setattr("src.ingestion.schema.apply_schema", MagicMock())
    monkeypatch.setattr("src.ingestion.load_metadata.load_metadata", MagicMock(return_value=1))
    monkeypatch.setattr("src.ingestion.embeddings.index_papers.run_embedding", MagicMock(return_value=1))
    monkeypatch.setattr("src.ingestion.validate.run_validation", MagicMock(return_value=[]))
    monkeypatch.setattr(
        jobs, "_run_extraction_followup", MagicMock(side_effect=RuntimeError("llm backend unreachable"))
    )

    result = jobs.run_ingest_job("ingest-uploads/job-5/papers.jsonl", run_extraction=True)

    assert result["loaded"] == 1  # ingestion is still reported as successful
    assert result["extraction"]["error"] == "llm backend unreachable"
    fake_driver.close.assert_called_once()


def test_run_ingest_job_without_extraction_flag_skips_followup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jobs, "get_minio_client", lambda: MagicMock())
    monkeypatch.setattr(jobs, "_write_driver", lambda: MagicMock())
    monkeypatch.setattr(jobs, "_get_embedding_model", lambda: object())
    monkeypatch.setattr("src.ingestion.schema.apply_schema", MagicMock())
    monkeypatch.setattr("src.ingestion.load_metadata.load_metadata", MagicMock(return_value=1))
    monkeypatch.setattr("src.ingestion.embeddings.index_papers.run_embedding", MagicMock(return_value=1))
    monkeypatch.setattr("src.ingestion.validate.run_validation", MagicMock(return_value=[]))

    fake_followup = MagicMock()
    monkeypatch.setattr(jobs, "_run_extraction_followup", fake_followup)

    result = jobs.run_ingest_job("ingest-uploads/job-6/papers.jsonl")

    fake_followup.assert_not_called()
    assert "extraction" not in result
