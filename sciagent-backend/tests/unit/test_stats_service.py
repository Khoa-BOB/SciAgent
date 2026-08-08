"""Unit tests for kg_service.services.stats -- specs/04-kg-service-nfr-testing-deployment.md §5."""

from unittest.mock import MagicMock

from kg_service.services import stats as stats_service


def test_get_corpus_stats_translates_record() -> None:
    driver = MagicMock()
    driver.execute_query.return_value = (
        [
            {
                "paper_count": 36009,
                "author_count": 128441,
                "category_count": 176,
                "method_count": 4213,
                "dataset_count": 1876,
                "topic_count": 5502,
                "papers_with_entities": 35981,
            }
        ],
        None,
        None,
    )

    stats = stats_service.get_corpus_stats(driver=driver)

    assert stats.paper_count == 36009
    assert stats.entity_counts == {"method": 4213, "dataset": 1876, "topic": 5502}
    assert stats.papers_with_entities == 35981
