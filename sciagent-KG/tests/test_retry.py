import pytest

from src.ingestion.retry import with_retry


def test_with_retry_succeeds_after_transient_failures(monkeypatch):
    monkeypatch.setattr("src.ingestion.retry.time.sleep", lambda _seconds: None)

    calls = {"count": 0}

    def flaky():
        calls["count"] += 1
        if calls["count"] < 3:
            raise ConnectionError("not ready yet")
        return "ok"

    result = with_retry(flaky, retries=5, base_delay=0.01, retryable=(ConnectionError,))

    assert result == "ok"
    assert calls["count"] == 3


def test_with_retry_gives_up_after_max_retries(monkeypatch):
    monkeypatch.setattr("src.ingestion.retry.time.sleep", lambda _seconds: None)

    def always_fails():
        raise ConnectionError("still not ready")

    with pytest.raises(ConnectionError):
        with_retry(always_fails, retries=2, base_delay=0.01, retryable=(ConnectionError,))


def test_with_retry_does_not_catch_non_retryable_errors(monkeypatch):
    monkeypatch.setattr("src.ingestion.retry.time.sleep", lambda _seconds: None)

    def raises_value_error():
        raise ValueError("not retryable")

    with pytest.raises(ValueError):
        with_retry(raises_value_error, retries=5, base_delay=0.01, retryable=(ConnectionError,))
