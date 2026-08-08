"""specs/04-mcp-nfr-testing-deployment.md §6 -- fail-fast on missing config.

validate_config() is called at process startup (mcp_service/server.py's
main()), not at import time, so tests patch the already-imported module
constants directly rather than env vars.
"""

import pytest

from mcp_service import config


def test_validate_config_passes_with_both_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "KG_SERVICE_API_KEY", "outbound-key")
    monkeypatch.setattr(config, "MCP_ALLOWED_KEYS", {"inbound-key"})

    config.validate_config()  # must not raise


def test_validate_config_rejects_missing_outbound_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "KG_SERVICE_API_KEY", "")
    monkeypatch.setattr(config, "MCP_ALLOWED_KEYS", {"inbound-key"})

    with pytest.raises(EnvironmentError, match="KG_SERVICE_API_KEY"):
        config.validate_config()


def test_validate_config_rejects_empty_allowed_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "KG_SERVICE_API_KEY", "outbound-key")
    monkeypatch.setattr(config, "MCP_ALLOWED_KEYS", set())

    with pytest.raises(EnvironmentError, match="MCP_ALLOWED_KEYS"):
        config.validate_config()
