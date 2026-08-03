-- check: papers_without_authors
-- description: Every paper must have at least one AUTHORED relationship
MATCH (p:Paper) WHERE NOT (p)<-[:AUTHORED]-() RETURN count(p) AS violations;

-- check: papers_without_categories
-- description: Every paper must belong to at least one category
MATCH (p:Paper) WHERE NOT (p)-[:IN_CATEGORY]->() RETURN count(p) AS violations;

-- check: papers_missing_title_or_abstract
-- description: title and abstract are required Paper properties
MATCH (p:Paper) WHERE p.title IS NULL OR p.abstract IS NULL RETURN count(p) AS violations;

-- check: duplicate_author_positions
-- description: AUTHORED.position must not repeat within a single paper
MATCH (p:Paper)<-[r:AUTHORED]-()
WITH p, r.position AS position, count(*) AS occurrences
WHERE occurrences > 1
RETURN count(*) AS violations;

-- check: non_positive_version_numbers
-- description: Version.version_number must be greater than 0
MATCH (v:Version) WHERE v.version_number <= 0 RETURN count(v) AS violations;

-- check: papers_with_multiple_submitters
-- description: A paper may have zero or one submitter, never more than one
MATCH (p:Paper)<-[:SUBMITTED]-(s)
WITH p, count(s) AS submitter_count
WHERE submitter_count > 1
RETURN count(p) AS violations;
