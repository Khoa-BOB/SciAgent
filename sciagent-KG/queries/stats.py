"""Corpus-level aggregate counts, added for sciagent-backend's KG Service
(specs/02-kg-service-architecture.md §8: additive-only, small new query).

Each CALL () {...} block is an uncorrelated subquery -- runs independently
and returns exactly one row, so combining seven of them is a cheap cartesian
product of seven single-row results rather than an actual join.
"""

CORPUS_STATS = """
CALL () { MATCH (p:Paper) RETURN count(p) AS paper_count }
CALL () { MATCH (a:Author) RETURN count(a) AS author_count }
CALL () { MATCH (c:Category) RETURN count(c) AS category_count }
CALL () { MATCH (m:Method) RETURN count(m) AS method_count }
CALL () { MATCH (d:Dataset) RETURN count(d) AS dataset_count }
CALL () { MATCH (t:ResearchTopic) RETURN count(t) AS topic_count }
CALL () {
    MATCH (p:Paper)
    WHERE (p)-[:USES_METHOD|USES_DATASET|STUDIES_TOPIC]->()
    RETURN count(DISTINCT p) AS papers_with_entities
}
RETURN paper_count, author_count, category_count,
       method_count, dataset_count, topic_count, papers_with_entities
"""
