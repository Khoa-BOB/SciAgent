SEED_CONTEXT = """
UNWIND $paper_ids AS paper_id
MATCH (p:Paper {arxiv_id: paper_id})
OPTIONAL MATCH (p)<-[:AUTHORED]-(a:Author)
OPTIONAL MATCH (p)-[:IN_CATEGORY]->(c:Category)
OPTIONAL MATCH (p)-[:PUBLISHED_IN]->(j:Journal)
WITH p, j,
     collect(DISTINCT a.display_name) AS authors,
     collect(DISTINCT c.code) AS categories
RETURN p.arxiv_id AS paper_id,
       authors,
       categories,
       j.name AS journal
"""

RELATED_BY_AUTHOR = """
UNWIND $paper_ids AS paper_id
MATCH (:Paper {arxiv_id: paper_id})<-[:AUTHORED]-(a:Author)-[:AUTHORED]->(related:Paper)
WHERE NOT related.arxiv_id IN $paper_ids
WITH related, collect(DISTINCT a.display_name) AS shared_authors
RETURN related.arxiv_id AS paper_id,
       related.title AS title,
       related.embedding AS embedding,
       shared_authors
ORDER BY size(shared_authors) DESC
LIMIT $pool_size
"""

RELATED_BY_CATEGORY = """
UNWIND $paper_ids AS paper_id
MATCH (:Paper {arxiv_id: paper_id})-[:IN_CATEGORY {primary: true}]->(c:Category)
      <-[:IN_CATEGORY {primary: true}]-(related:Paper)
WHERE NOT related.arxiv_id IN $paper_ids
WITH related, collect(DISTINCT c.code) AS shared_categories
RETURN related.arxiv_id AS paper_id,
       related.title AS title,
       related.embedding AS embedding,
       shared_categories
ORDER BY size(shared_categories) DESC
LIMIT $pool_size
"""
