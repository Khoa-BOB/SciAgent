"""Unit test for the service-key allowlist check -- specs/04-kg-service-nfr-testing-deployment.md §5."""

import pytest

from kg_service.errors import ApiError


def test_missing_key_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("kg_service.auth.ALLOWED_SERVICE_KEYS", {"known-key"})
    from kg_service.auth import require_service_key

    with pytest.raises(ApiError):
        require_service_key(None)


def test_unknown_key_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("kg_service.auth.ALLOWED_SERVICE_KEYS", {"known-key"})
    from kg_service.auth import require_service_key

    with pytest.raises(ApiError):
        require_service_key("wrong-key")


def test_known_key_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("kg_service.auth.ALLOWED_SERVICE_KEYS", {"known-key"})
    from kg_service.auth import require_service_key

    assert require_service_key("known-key") == "known-key"
