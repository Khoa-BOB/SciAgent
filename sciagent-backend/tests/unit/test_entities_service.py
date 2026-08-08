"""Unit tests for kg_service.services.entities -- specs/04-kg-service-nfr-testing-deployment.md §5."""

from unittest.mock import MagicMock

import pytest

from kg_service.errors import ApiError, ErrorCode
from kg_service.services import entities as entities_service


def test_get_paper_entities_raises_when_paper_missing() -> None:
    driver = MagicMock()
    driver.execute_query.return_value = ([], None, None)

    with pytest.raises(ApiError) as exc_info:
        entities_service.get_paper_entities(driver=driver, arxiv_id="9999.99999")
    assert exc_info.value.code == ErrorCode.PAPER_NOT_FOUND
    assert exc_info.value.status_code == 404


def test_get_paper_entities_translates_record() -> None:
    driver = MagicMock()
    driver.execute_query.return_value = (
        [
            {
                "paper_id": "2401.12345",
                "methods": [{"name": "Graph Attention Network", "confidence": 0.9}],
                "datasets": [],
                "topics": [{"name": "molecular property prediction", "confidence": 0.8}],
            }
        ],
        None,
        None,
    )

    result = entities_service.get_paper_entities(driver=driver, arxiv_id="2401.12345")

    assert result.paper_id == "2401.12345"
    assert result.methods[0].name == "Graph Attention Network"
    assert result.methods[0].confidence == 0.9
    assert result.datasets == []
    assert result.topics[0].name == "molecular property prediction"


def test_list_entities_translates_records() -> None:
    driver = MagicMock()
    driver.execute_query.return_value = (
        [{"name": "Graph Attention Network", "normalized_name": "graph attention network"}],
        None,
        None,
    )

    results = entities_service.list_entities(driver=driver, entity_type="method", query=None, limit=20)

    assert results[0].name == "Graph Attention Network"
    assert results[0].normalized_name == "graph attention network"


def test_papers_for_entity_raises_when_entity_missing() -> None:
    driver = MagicMock()
    driver.execute_query.return_value = ([], None, None)

    with pytest.raises(ApiError) as exc_info:
        entities_service.papers_for_entity(
            driver=driver, entity_type="dataset", normalized_name="nonexistent", limit=20
        )
    assert exc_info.value.code == ErrorCode.ENTITY_NOT_FOUND
    assert exc_info.value.status_code == 404


def test_papers_for_entity_translates_records_when_entity_exists() -> None:
    driver = MagicMock()
    driver.execute_query.side_effect = [
        ([{"normalized_name": "ogbn-arxiv"}], None, None),  # entity_exists_query
        ([{"paper_id": "2401.12345", "title": "T", "confidence": 0.85}], None, None),  # papers_for_entity_query
    ]

    results = entities_service.papers_for_entity(driver=driver, entity_type="dataset", normalized_name="ogbn-arxiv", limit=20)

    assert results[0].paper_id == "2401.12345"
    assert results[0].confidence == 0.85
    assert driver.execute_query.call_count == 2
