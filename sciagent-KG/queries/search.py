PAPER_BY_ID = """
MATCH (p:Paper {arxiv_id: $paper_id})
RETURN p.arxiv_id AS paper_id, p.title AS title, p.abstract AS abstract,
       p.embedding AS embedding
"""

# Richer than PAPER_BY_ID -- used by sciagent-backend's GET /v1/papers/{arxiv_id}
# (specs/03-kg-service-api-spec.md §2), which needs authors/categories/journal/
# doi/update_date/versions but never the embedding. Kept separate from
# PAPER_BY_ID rather than extending it, since PAPER_BY_ID's embedding-only
# callers (vector reranking, `by-id` CLI) don't need this extra join cost.
PAPER_DETAIL = """
MATCH (p:Paper {arxiv_id: $paper_id})
CALL (p) {
    MATCH (a:Author)-[r:AUTHORED]->(p)
    RETURN a.display_name AS name
    ORDER BY r.position
}
WITH p, collect(name) AS authors
CALL (p) {
    MATCH (p)-[r:IN_CATEGORY]->(c:Category)
    RETURN c.code AS code
    ORDER BY r.position
}
WITH p, authors, collect(code) AS categories
CALL (p) {
    OPTIONAL MATCH (p)-[pub:PUBLISHED_IN]->(:Journal)
    RETURN pub.journal_reference_raw AS journal
    LIMIT 1
}
WITH p, authors, categories, journal
CALL (p) {
    MATCH (p)-[:HAS_VERSION]->(v:Version)
    RETURN v.label AS label
    ORDER BY v.version_number
}
WITH p, authors, categories, journal, collect(label) AS versions
RETURN p.arxiv_id AS paper_id, p.title AS title, p.abstract AS abstract,
       authors, categories, journal, p.doi AS doi,
       toString(p.update_date) AS update_date, versions
"""

# Existence check for a category code -- lets the API distinguish "valid
# code, zero papers" from "typo'd code" (specs/03-kg-service-api-spec.md §3,
# CATEGORY_NOT_FOUND).
CATEGORY_EXISTS = """
MATCH (c:Category {code: $category_code})
RETURN c.code AS code
LIMIT 1
"""

PAPERS_BY_AUTHOR = """
MATCH (a:Author)-[:AUTHORED]->(p:Paper)
WHERE a.normalized_name CONTAINS $normalized_name
RETURN DISTINCT p.arxiv_id AS paper_id, p.title AS title, p.abstract AS abstract,
       a.display_name AS author_name, p.update_date AS update_date
ORDER BY update_date DESC
LIMIT $limit
"""

PAPERS_BY_CATEGORY = """
MATCH (p:Paper)-[:IN_CATEGORY]->(:Category {code: $category_code})
RETURN p.arxiv_id AS paper_id, p.title AS title, p.abstract AS abstract
ORDER BY p.update_date DESC
LIMIT $limit
"""

PAPERS_BY_YEAR = """
MATCH (p:Paper)
WHERE p.first_submitted_at.year >= $start_year AND p.first_submitted_at.year <= $end_year
RETURN p.arxiv_id AS paper_id, p.title AS title, p.abstract AS abstract,
       p.first_submitted_at AS first_submitted_at
ORDER BY p.first_submitted_at DESC
LIMIT $limit
"""

FULLTEXT_SEARCH = """
CALL db.index.fulltext.queryNodes('paper_text', $query_text)
YIELD node, score
RETURN node.arxiv_id AS paper_id, node.title AS title, node.abstract AS abstract, score
ORDER BY score DESC
LIMIT $limit
"""
