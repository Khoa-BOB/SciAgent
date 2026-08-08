"""Unit tests for the write-scoped service-key allowlist -- a separate,
smaller allowlist than require_service_key's, gating only /v1/ingest-jobs.
See specs/02-kg-service-architecture.md §8.
"""

import pytest

from kg_service.errors import ApiError


def test_missing_key_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("kg_service.auth.WRITE_ALLOWED_SERVICE_KEYS", {"known-write-key"})
    from kg_service.auth import require_write_service_key

    with pytest.raises(ApiError):
        require_write_service_key(None)


def test_unknown_key_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("kg_service.auth.WRITE_ALLOWED_SERVICE_KEYS", {"known-write-key"})
    from kg_service.auth import require_write_service_key

    with pytest.raises(ApiError):
        require_write_service_key("wrong-key")


def test_read_only_key_rejected_for_write(monkeypatch: pytest.MonkeyPatch) -> None:
    """A key valid for read-only endpoints must not also work for the write path."""
    monkeypatch.setattr("kg_service.auth.ALLOWED_SERVICE_KEYS", {"read-only-key"})
    monkeypatch.setattr("kg_service.auth.WRITE_ALLOWED_SERVICE_KEYS", {"known-write-key"})
    from kg_service.auth import require_write_service_key

    with pytest.raises(ApiError):
        require_write_service_key("read-only-key")


def test_known_write_key_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("kg_service.auth.WRITE_ALLOWED_SERVICE_KEYS", {"known-write-key"})
    from kg_service.auth import require_write_service_key

    assert require_write_service_key("known-write-key") == "known-write-key"
