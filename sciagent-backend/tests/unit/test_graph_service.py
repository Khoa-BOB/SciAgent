"""Unit tests for kg_service.services.graph -- specs/04-kg-service-nfr-testing-deployment.md §5."""

from dataclasses import dataclass, field
from unittest.mock import MagicMock

from kg_service.schemas.graph import GraphExpandRequest
from kg_service.services import graph as graph_service


@dataclass
class _FakePaperContext:
    paper_id: str
    authors: list[str]
    categories: list[str]
    journal: str | None


@dataclass
class _FakeRelatedPaper:
    paper_id: str
    title: str
    shared_authors: list[str] = field(default_factory=list)
    shared_categories: list[str] = field(default_factory=list)
    similarity_to_query: float = 0.0


@dataclass
class _FakeExpandedResult:
    seed_context: dict
    related_papers: list


def test_expand_graph_translates_dataclasses_to_response(monkeypatch) -> None:
    fake_expander = MagicMock()
    fake_expander.expand.return_value = _FakeExpandedResult(
        seed_context={"2401.00001": _FakePaperContext("2401.00001", ["Jane Doe"], ["cs.AI"], None)},
        related_papers=[_FakeRelatedPaper("2312.00001", "Related", shared_authors=["Jane Doe"])],
    )
    monkeypatch.setattr(graph_service, "get_graph_expander", lambda: fake_expander)

    request = GraphExpandRequest(paper_ids=["2401.00001"], related_limit=5, pool_size=20)
    response = graph_service.expand_graph(driver=MagicMock(), request=request)

    fake_expander.expand.assert_called_once_with(
        paper_ids=["2401.00001"], query_embedding=None, related_limit=5, pool_size=20
    )
    assert response.seed_context["2401.00001"].authors == ["Jane Doe"]
    assert response.related_papers[0].paper_id == "2312.00001"
    assert response.related_papers[0].shared_authors == ["Jane Doe"]
