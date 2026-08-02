from queries.expansion import RELATED_BY_AUTHOR, RELATED_BY_CATEGORY, SEED_CONTEXT


def test_seed_context_returns_authors_categories_and_journal():
    assert "RETURN p.arxiv_id AS paper_id" in SEED_CONTEXT
    assert "authors" in SEED_CONTEXT
    assert "categories" in SEED_CONTEXT
    assert "j.name AS journal" in SEED_CONTEXT


def test_related_by_author_excludes_seed_papers():
    assert "WHERE NOT related.arxiv_id IN $paper_ids" in RELATED_BY_AUTHOR
    assert "related.embedding AS embedding" in RELATED_BY_AUTHOR
    assert "LIMIT $pool_size" in RELATED_BY_AUTHOR


def test_related_by_category_filters_primary_category_only():
    assert "IN_CATEGORY {primary: true}" in RELATED_BY_CATEGORY
    assert "WHERE NOT related.arxiv_id IN $paper_ids" in RELATED_BY_CATEGORY
    assert "related.embedding AS embedding" in RELATED_BY_CATEGORY
    assert "LIMIT $pool_size" in RELATED_BY_CATEGORY
