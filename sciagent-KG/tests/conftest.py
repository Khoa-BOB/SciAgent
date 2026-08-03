import pytest


@pytest.fixture(autouse=True)
def isolate_checkpoints(tmp_path, monkeypatch):
    """Every test gets its own throwaway checkpoint directory so tests never
    read or write the real .checkpoints/ directory in the repo."""
    monkeypatch.setattr("src.ingestion.checkpoint.CHECKPOINT_DIR", tmp_path / ".checkpoints")


class FakeTransaction:
    def __init__(self, log: list):
        self.log = log

    def run(self, query, **kwargs):
        self.log.append((query, kwargs))


class FakeSession:
    def __init__(self, driver, database=None):
        self.driver = driver
        self.database = database

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute_write(self, fn, *args, **kwargs):
        batch_index = len(self.driver.batches)
        if batch_index in self.driver.fail_at_batches:
            raise self.driver.failure

        tx = FakeTransaction([])
        result = fn(tx, *args, **kwargs)
        self.driver.batches.append(tx.log)
        return result


class FakeMetadataDriver:
    """Fake neo4j Driver for load_metadata tests: records each committed batch
    as a list of (query, params) tuples, one entry per session.execute_write()
    call, so tests can assert on batch boundaries without a live Neo4j."""

    def __init__(self, fail_at_batches: set[int] | None = None, failure: Exception | None = None):
        self.batches: list[list[tuple[str, dict]]] = []
        self.fail_at_batches = fail_at_batches or set()
        self.failure = failure or RuntimeError("simulated batch failure")

    def session(self, database=None):
        return FakeSession(self, database=database)

    def close(self) -> None:
        pass
