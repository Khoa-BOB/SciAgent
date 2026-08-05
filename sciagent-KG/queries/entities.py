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
            r.extracted_at = row.extracted_at
    """
