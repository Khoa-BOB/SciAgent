from queries.search import (
    FULLTEXT_SEARCH,
    PAPER_BY_ID,
    PAPERS_BY_AUTHOR,
    PAPERS_BY_CATEGORY,
    PAPERS_BY_YEAR,
)


def test_paper_by_id_returns_embedding():
    assert "MATCH (p:Paper {arxiv_id: $paper_id})" in PAPER_BY_ID
    assert "p.embedding AS embedding" in PAPER_BY_ID


def test_papers_by_author_matches_normalized_name():
    assert "a.normalized_name CONTAINS $normalized_name" in PAPERS_BY_AUTHOR
    assert "LIMIT $limit" in PAPERS_BY_AUTHOR


def test_papers_by_category_filters_by_category_code():
    assert "IN_CATEGORY]->(:Category {code: $category_code})" in PAPERS_BY_CATEGORY
    assert "LIMIT $limit" in PAPERS_BY_CATEGORY


def test_papers_by_year_filters_by_submission_year_range():
    assert "p.first_submitted_at.year >= $start_year" in PAPERS_BY_YEAR
    assert "p.first_submitted_at.year <= $end_year" in PAPERS_BY_YEAR
    assert "LIMIT $limit" in PAPERS_BY_YEAR


def test_fulltext_search_uses_paper_text_index():
    assert "db.index.fulltext.queryNodes('paper_text'" in FULLTEXT_SEARCH
    assert "LIMIT $limit" in FULLTEXT_SEARCH
