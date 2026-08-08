"""Unit tests for kg_service.services.search -- specs/04-kg-service-nfr-testing-deployment.md §5.

Mocks the cached PaperSearch/PaperVectorSearch singletons and the Neo4j
driver directly, so these run without a live Neo4j instance or downloading
the embedding model -- see specs/05-mcp-roadmap.md's note that true
fixture-graph integration tests are a follow-up once Neo4j test infra
exists.
"""

from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from kg_service.errors import ApiError, ErrorCode
from kg_service.services import search as search_service


@dataclass
class _FakeSummary:
    paper_id: str
    title: str
    abstract: str
    score: float | None = None
    matched_by: str | None = None


def test_search_fulltext_translates_results(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_search = MagicMock()
    fake_search.search_fulltext.return_value = [_FakeSummary("2401.00001", "T", "A", score=4.2)]
    monkeypatch.setattr(search_service, "get_paper_search", lambda: fake_search)

    results = search_service.search_fulltext(driver=MagicMock(), query_text="graphs", limit=10)

    fake_search.search_fulltext.assert_called_once_with("graphs", limit=10)
    assert results[0].paper_id == "2401.00001"
    assert results[0].score == 4.2


def test_search_semantic_translates_results(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_vector_search = MagicMock()
    fake_vector_search.search.return_value = [_FakeSummary("2401.00002", "T", "A", score=0.9)]
    monkeypatch.setattr(search_service, "get_vector_search", lambda: fake_vector_search)

    results = search_service.search_semantic(driver=MagicMock(), query_text="gnn", top_k=5)

    fake_vector_search.search.assert_called_once_with("gnn", top_k=5)
    assert results == [search_service._to_summary(_FakeSummary("2401.00002", "T", "A", score=0.9))]


def test_search_semantic_by_embedding_rejects_wrong_dimension() -> None:
    with pytest.raises(ApiError) as exc_info:
        search_service.search_semantic_by_embedding(driver=MagicMock(), embedding=[0.1, 0.2], top_k=5)
    assert exc_info.value.code == ErrorCode.INVALID_EMBEDDING_DIMENSION
    assert exc_info.value.status_code == 422


def test_search_semantic_by_embedding_accepts_correct_dimension(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_vector_search = MagicMock()
    fake_vector_search.search_by_embedding.return_value = []
    monkeypatch.setattr(search_service, "get_vector_search", lambda: fake_vector_search)

    embedding = [0.0] * search_service.EMBEDDING_DIMENSIONS
    search_service.search_semantic_by_embedding(driver=MagicMock(), embedding=embedding, top_k=5)

    fake_vector_search.search_by_embedding.assert_called_once_with(embedding, top_k=5)


def test_search_by_category_raises_when_category_missing() -> None:
    driver = MagicMock()
    driver.execute_query.return_value = ([], None, None)

    with pytest.raises(ApiError) as exc_info:
        search_service.search_by_category(driver=driver, code="zz.ZZ", limit=10)
    assert exc_info.value.code == ErrorCode.CATEGORY_NOT_FOUND
    assert exc_info.value.status_code == 404


def test_search_by_category_delegates_when_category_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    driver = MagicMock()
    driver.execute_query.return_value = ([SimpleNamespace()], None, None)
    fake_search = MagicMock()
    fake_search.search_by_category.return_value = [_FakeSummary("2401.00003", "T", "A")]
    monkeypatch.setattr(search_service, "get_paper_search", lambda: fake_search)

    results = search_service.search_by_category(driver=driver, code="cs.AI", limit=10)

    fake_search.search_by_category.assert_called_once_with("cs.AI", limit=10)
    assert results[0].paper_id == "2401.00003"


def test_search_by_year_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_search = MagicMock()
    fake_search.search_by_year.return_value = [_FakeSummary("2401.00004", "T", "A", matched_by="2024")]
    monkeypatch.setattr(search_service, "get_paper_search", lambda: fake_search)

    results = search_service.search_by_year(driver=MagicMock(), start_year=2024, end_year=2024, limit=10)

    fake_search.search_by_year.assert_called_once_with(2024, end_year=2024, limit=10)
    assert results[0].matched_by == "2024"


def test_search_by_author_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_search = MagicMock()
    fake_search.search_by_author.return_value = [_FakeSummary("2401.00005", "T", "A", matched_by="Jane Doe")]
    monkeypatch.setattr(search_service, "get_paper_search", lambda: fake_search)

    results = search_service.search_by_author(driver=MagicMock(), name="Jane", limit=10)

    fake_search.search_by_author.assert_called_once_with("Jane", limit=10)
    assert results[0].matched_by == "Jane Doe"
