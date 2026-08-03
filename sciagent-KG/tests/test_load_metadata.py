import json
from pathlib import Path

import pytest

from src.ingestion.checkpoint import load_checkpoint, save_checkpoint
from src.ingestion.load_metadata import load_metadata
from tests.conftest import FakeMetadataDriver


def _write_records(path: Path, n: int) -> None:
    with path.open("w", encoding="utf-8") as f:
        for i in range(1, n + 1):
            f.write(json.dumps({"id": f"1000.{i:04d}"}) + "\n")


def test_load_metadata_batches_writes(tmp_path):
    metadata_path = tmp_path / "papers.jsonl"
    _write_records(metadata_path, 5)

    driver = FakeMetadataDriver()
    loaded = load_metadata(metadata_path, driver, batch_size=2, resume=False)

    assert loaded == 5
    assert [len(batch) for batch in driver.batches] == [2, 2, 1]


def test_load_metadata_resumes_from_checkpoint(tmp_path):
    metadata_path = tmp_path / "papers.jsonl"
    _write_records(metadata_path, 5)

    driver = FakeMetadataDriver()
    loaded = load_metadata(metadata_path, driver, batch_size=2, resume=True)
    assert loaded == 5

    # Re-running against the unchanged file should skip everything already
    # checkpointed instead of reprocessing from line 1.
    driver_again = FakeMetadataDriver()
    loaded_again = load_metadata(metadata_path, driver_again, batch_size=2, resume=True)

    assert loaded_again == 0
    assert driver_again.batches == []


def test_load_metadata_resumes_from_partial_checkpoint(tmp_path):
    metadata_path = tmp_path / "papers.jsonl"
    _write_records(metadata_path, 5)

    # Simulate a prior run that only got through line 3.
    save_checkpoint(metadata_path, last_line=3, last_arxiv_id="1000.0003")

    driver = FakeMetadataDriver()
    loaded = load_metadata(metadata_path, driver, batch_size=2, resume=True)

    assert loaded == 2
    assert [len(batch) for batch in driver.batches] == [2]
    all_params = [params for query, params in driver.batches[0]]
    assert {p["arxiv_id"] for p in all_params} == {"1000.0004", "1000.0005"}


def test_load_metadata_failed_batch_checkpoints_last_good_batch(tmp_path):
    metadata_path = tmp_path / "papers.jsonl"
    _write_records(metadata_path, 5)

    # Batch index 1 (the second flush, lines 3-4) fails.
    driver = FakeMetadataDriver(fail_at_batches={1})

    with pytest.raises(RuntimeError):
        load_metadata(metadata_path, driver, batch_size=2, resume=False)

    # Only the first batch (lines 1-2) succeeded before the failure.
    assert [len(batch) for batch in driver.batches] == [2]

    checkpoint = load_checkpoint(metadata_path)
    assert checkpoint is not None
    assert checkpoint.last_line == 2
    assert checkpoint.last_arxiv_id == "1000.0002"
