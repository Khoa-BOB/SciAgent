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
    """`row.embedding` is only ever present for a canonical entity that's
    genuinely new in this merge run (src/extraction/resolve.py's
    new_canonical_embeddings) -- an existing entity already has one stored,
    and ON CREATE SET simply doesn't fire for a MERGE that matched an
    existing node, so this never overwrites it. See
    src/extraction/merge.py's fetch_existing_clusters()/backfill_entity_embeddings()
    for how entities end up with an embedding in the first place."""
    label = ENTITY_LABELS[entity_type]
    return f"""
        UNWIND $rows AS row
        MERGE (e:{label} {{normalized_name: row.normalized_name}})
        ON CREATE SET e.name = row.name, e.embedding = row.embedding
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


# --- Incremental resolve support (src/extraction/merge.py) -----------------
# specs/02-kg-service-architecture.md §8.5: lets a small, new batch of raw
# entity mentions cluster against every canonical entity already in the
# graph without re-embedding/re-reading the whole historical corpus.

def entities_with_embeddings_query(entity_type: str) -> str:
    """Every canonical entity of this type that already has an embedding
    stored -- the seed set for src.extraction.resolve.cluster_names()'s
    `existing_clusters` parameter."""
    label = ENTITY_LABELS[entity_type]
    return f"""
        MATCH (e:{label})
        WHERE e.embedding IS NOT NULL
        RETURN e.name AS name, e.embedding AS embedding
    """


def entities_missing_embedding_query(entity_type: str) -> str:
    """Canonical entities created before this feature existed (or by a
    caller that didn't pass one) -- the backfill target for
    merge.backfill_entity_embeddings()."""
    label = ENTITY_LABELS[entity_type]
    return f"""
        MATCH (e:{label})
        WHERE e.embedding IS NULL
        RETURN e.normalized_name AS normalized_name, e.name AS name
    """


def set_entity_embeddings_query(entity_type: str) -> str:
    """Backfill write: SET (not ON CREATE SET) since these nodes already
    exist -- merge.backfill_entity_embeddings() is the only caller, and only
    ever targets nodes entities_missing_embedding_query() just returned."""
    label = ENTITY_LABELS[entity_type]
    return f"""
        UNWIND $rows AS row
        MATCH (e:{label} {{normalized_name: row.normalized_name}})
        SET e.embedding = row.embedding
    """
