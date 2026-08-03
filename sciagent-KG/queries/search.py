PAPER_BY_ID = """
MATCH (p:Paper {arxiv_id: $paper_id})
RETURN p.arxiv_id AS paper_id, p.title AS title, p.abstract AS abstract,
       p.embedding AS embedding
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
