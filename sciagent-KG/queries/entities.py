"""Cypher for the extracted domain-entity layer (Method/Dataset/ResearchTopic).

One query template per statement, parameterized by entity type instead of
duplicated three times -- the label/relationship names are looked up from a
fixed internal dict (never taken from extracted text), so string-building
the query is safe.
"""

ENTITY_LABELS: dict[str, str] = {
    "method": "Method",
    "dataset": "Dataset",
    "topic": "ResearchTopic",
}

RELATION_TYPES: dict[str, str] = {
    "method": "USES_METHOD",
    "dataset": "USES_DATASET",
    "topic": "STUDIES_TOPIC",
}


def upsert_entities_query(entity_type: str) -> str:
    label = ENTITY_LABELS[entity_type]
    return f"""
        UNWIND $rows AS row
        MERGE (e:{label} {{normalized_name: row.normalized_name}})
        ON CREATE SET e.name = row.name
    """


def upsert_relations_query(entity_type: str) -> str:
    label = ENTITY_LABELS[entity_type]
    relation = RELATION_TYPES[entity_type]
    return f"""
        UNWIND $rows AS row
        MATCH (p:Paper {{arxiv_id: row.paper_id}})
        MATCH (e:{label} {{normalized_name: row.normalized_name}})
        MERGE (p)-[r:{relation}]->(e)
        SET r.confidence = row.confidence,
            r.extraction_model = row.extraction_model,
            r.extracted_at = row.extracted_at,
            r.raw_name = row.raw_name
    """


# Read-side templates below, added for sciagent-backend's KG Service
# (specs/02-kg-service-architecture.md §8: additive-only, same fixed-dict
# parameterization as the upsert templates above -- entity_type strings from
# callers are validated against ENTITY_LABELS/RELATION_TYPES before they
# ever reach an f-string, never taken from request text directly).

# Fixed, hardcoded label/relationship names (not parameterized -- there are
# only ever these three types, and get_paper_entities always returns all
# three regardless of which the caller cares about, so there's no per-call
# entity_type to look up). Each CALL (p) subquery runs independently, so a
# paper with e.g. many methods and few datasets doesn't cartesian-multiply
# the other lists -- same pattern queries/metadata.py's UPSERT_PAPER uses
# for authors/categories/versions.
ENTITIES_FOR_PAPER = """
MATCH (p:Paper {arxiv_id: $paper_id})
CALL (p) {
    MATCH (p)-[r:USES_METHOD]->(m:Method)
    RETURN collect({name: m.name, confidence: r.confidence}) AS methods
}
CALL (p) {
    MATCH (p)-[r:USES_DATASET]->(d:Dataset)
    RETURN collect({name: d.name, confidence: r.confidence}) AS datasets
}
CALL (p) {
    MATCH (p)-[r:STUDIES_TOPIC]->(t:ResearchTopic)
    RETURN collect({name: t.name, confidence: r.confidence}) AS topics
}
RETURN p.arxiv_id AS paper_id, methods, datasets, topics
"""


def list_entities_query(entity_type: str) -> str:
    """Browse/search entities of one type by optional name substring."""
    label = ENTITY_LABELS[entity_type]
    return f"""
        MATCH (e:{label})
        WHERE $query IS NULL OR toLower(e.name) CONTAINS toLower($query)
        RETURN e.name AS name, e.normalized_name AS normalized_name
        ORDER BY e.name
        LIMIT $limit
    """


def entity_exists_query(entity_type: str) -> str:
    """Existence check -- lets the API distinguish 'entity not found' from
    'entity exists but has zero papers' (specs/03-kg-service-api-spec.md §5,
    ENTITY_NOT_FOUND)."""
    label = ENTITY_LABELS[entity_type]
    return f"""
        MATCH (e:{label} {{normalized_name: $normalized_name}})
        RETURN e.normalized_name AS normalized_name
        LIMIT 1
    """


def papers_for_entity_query(entity_type: str) -> str:
    """Reverse lookup: papers that use/study a given entity."""
    label = ENTITY_LABELS[entity_type]
    relation = RELATION_TYPES[entity_type]
    return f"""
        MATCH (e:{label} {{normalized_name: $normalized_name}})<-[r:{relation}]-(p:Paper)
        RETURN p.arxiv_id AS paper_id, p.title AS title, r.confidence AS confidence
        ORDER BY r.confidence DESC
        LIMIT $limit
    """
