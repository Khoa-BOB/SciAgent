"""Unit tests for kg_service.services.papers -- specs/04-kg-service-nfr-testing-deployment.md §5.

Covers the field-completeness gap closed in this change (authors/categories/
journal/doi/update_date/versions were previously hardcoded empty -- see
specs/05-mcp-roadmap.md Sprint C).
"""

from unittest.mock import MagicMock

import pytest

from kg_service.errors import ApiError, ErrorCode
from kg_service.services import papers as papers_service


def test_get_paper_raises_when_missing() -> None:
    driver = MagicMock()
    driver.execute_query.return_value = ([], None, None)

    with pytest.raises(ApiError) as exc_info:
        papers_service.get_paper(driver=driver, arxiv_id="9999.99999")
    assert exc_info.value.code == ErrorCode.PAPER_NOT_FOUND
    assert exc_info.value.status_code == 404


def test_get_paper_returns_full_detail() -> None:
    driver = MagicMock()
    driver.execute_query.return_value = (
        [
            {
                "paper_id": "0704.0001",
                "title": "Calculation of prompt diphoton production cross sections",
                "abstract": "A fully differential calculation...",
                "authors": ["C. Balázs", "E. L. Berger"],
                "categories": ["hep-ph"],
                "journal": "Phys.Rev.D76:013009,2007",
                "doi": "10.1103/PhysRevD.76.013009",
                "update_date": "2008-11-26",
                "versions": ["v1", "v2"],
            }
        ],
        None,
        None,
    )

    detail = papers_service.get_paper(driver=driver, arxiv_id="0704.0001")

    assert detail.authors == ["C. Balázs", "E. L. Berger"]
    assert detail.categories == ["hep-ph"]
    assert detail.journal == "Phys.Rev.D76:013009,2007"
    assert detail.doi == "10.1103/PhysRevD.76.013009"
    assert detail.update_date == "2008-11-26"
    assert detail.versions == ["v1", "v2"]
