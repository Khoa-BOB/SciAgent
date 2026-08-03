import pytest

from src import config


def test_validate_config_raises_on_missing_vars(monkeypatch):
    monkeypatch.setattr(config, "NEO4J_URI", None)
    monkeypatch.setattr(config, "NEO4J_USERNAME", "neo4j")
    monkeypatch.setattr(config, "NEO4J_PASSWORD", None)

    with pytest.raises(EnvironmentError) as exc_info:
        config.validate_config()

    assert "NEO4J_URI" in str(exc_info.value)
    assert "NEO4J_PASSWORD" in str(exc_info.value)
    assert "NEO4J_USERNAME" not in str(exc_info.value)


def test_validate_config_passes_when_all_set(monkeypatch):
    monkeypatch.setattr(config, "NEO4J_URI", "bolt://localhost:7687")
    monkeypatch.setattr(config, "NEO4J_USERNAME", "neo4j")
    monkeypatch.setattr(config, "NEO4J_PASSWORD", "secret")

    config.validate_config()  # should not raise
