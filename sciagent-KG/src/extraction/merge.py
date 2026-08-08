import argparse
import json
import logging
from pathlib import Path
from typing import Any, Iterator, TypeVar

import numpy as np
from neo4j import Driver

from queries.entities import (
    ENTITY_LABELS,
    entities_missing_embedding_query,
    entities_with_embeddings_query,
    set_entity_embeddings_query,
    upsert_entities_query,
    upsert_relations_query,
)
from src.config import NEO4J_DATABASE, get_driver

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 500
T = TypeVar("T")


def read_resolved(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as resolved_file:
        for line in resolved_file:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def read_embeddings(path: Path) -> dict[str, dict[str, list[float]]]:
    """Companion file to a resolved.jsonl, written by cli.py's `resolve`
    command (src.extraction.resolve.resolve's new_embeddings_by_type,
    serialized) -- entity_type -> {normalized_name: embedding}. Returns {}
    if the file doesn't exist, so merge still works against an older
    resolved.jsonl that predates this feature."""
    if not path.exists():
        return {}

    embeddings: dict[str, dict[str, list[float]]] = {}
    with path.open(encoding="utf-8") as embeddings_file:
        for line in embeddings_file:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            embeddings.setdefault(record["entity_type"], {})[record["normalized_name"]] = record["embedding"]
    return embeddings


def _chunks(items: list[T], size: int) -> Iterator[list[T]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _as_list(embedding: Any) -> list[float]:
    return embedding.tolist() if isinstance(embedding, np.ndarray) else embedding


def merge_resolved(
    driver: Driver,
    database: str | None,
    rows: list[dict],
    new_embeddings: dict[str, dict[str, Any]] | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> tuple[int, int]:
    """Upsert resolved (paper, entity) rows into Neo4j: one Method/Dataset/
    ResearchTopic node per unique normalized_name, one USES_METHOD/
    USES_DATASET/STUDIES_TOPIC relationship per (paper, entity) pair.

    Every write is MERGE-based, so this is safe to rerun on failure instead
    of needing its own checkpoint file -- unlike the LLM extraction stage,
    a full retry here costs nothing but some Neo4j round-trips.

    new_embeddings: entity_type -> {normalized_name: embedding}, from
    src.extraction.resolve.resolve()'s second return value (directly, or
    round-tripped through read_embeddings()). Only entities genuinely new in
    this run need one -- an existing entity already has one stored, and
    upsert_entities_query's ON CREATE SET doesn't fire for a MERGE that
    matched an existing node, so passing None here for an existing entity
    is harmless. Omit entirely for the pre-embedding-caching behavior
    (entities get created without one, same as before this feature).
    """
    by_type: dict[str, list[dict]] = {}
    for row in rows:
        by_type.setdefault(row["entity_type"], []).append(row)

    entities_written = 0
    relations_written = 0

    for entity_type, type_rows in by_type.items():
        type_new_embeddings = (new_embeddings or {}).get(entity_type, {})
        unique_entities = list(
            {
                row["normalized_name"]: {
                    "normalized_name": row["normalized_name"],
                    "name": row["name"],
                    "embedding": _as_list(type_new_embeddings[row["normalized_name"]])
                    if row["normalized_name"] in type_new_embeddings
                    else None,
                }
                for row in type_rows
            }.values()
        )
        for batch in _chunks(unique_entities, batch_size):
            driver.execute_query(upsert_entities_query(entity_type), rows=batch, database_=database)
            entities_written += len(batch)

        relation_rows = [
            {
                "paper_id": row["paper_id"],
                "normalized_name": row["normalized_name"],
                "confidence": row.get("confidence", 1.0),
                "extraction_model": row.get("extraction_model"),
                "extracted_at": row.get("extracted_at"),
                # Pre-clustering name as extracted, may differ from the
                # canonical entity name above -- kept on the relationship so
                # it survives independent of the resolve/extract JSONL files.
                "raw_name": row.get("raw_name"),
            }
            for row in type_rows
        ]
        for batch in _chunks(relation_rows, batch_size):
            driver.execute_query(upsert_relations_query(entity_type), rows=batch, database_=database)
            relations_written += len(batch)

        logger.info(
            "%s: upserted %d entit(y/ies), %d relationship(s)",
            entity_type, len(unique_entities), len(relation_rows),
        )

    return entities_written, relations_written


def fetch_existing_clusters(driver: Driver, database: str | None) -> dict[str, list[tuple[str, np.ndarray]]]:
    """Every canonical entity that already has a stored embedding, per type
    -- the `existing_clusters` seed for src.extraction.resolve.resolve()'s
    incremental mode (specs/02-kg-service-architecture.md §8.5 in
    sciagent-backend). An entity created before backfill_entity_embeddings()
    ran (or by a caller that didn't pass embeddings) is silently excluded --
    it just won't be a candidate to cluster into until it's backfilled."""
    existing: dict[str, list[tuple[str, np.ndarray]]] = {}
    for entity_type in ENTITY_LABELS:
        records, _, _ = driver.execute_query(
            entities_with_embeddings_query(entity_type), database_=database, routing_="r"
        )
        existing[entity_type] = [(record["name"], np.array(record["embedding"], dtype=np.float32)) for record in records]
    return existing


def backfill_entity_embeddings(
    driver: Driver, database: str | None, model, batch_size: int = DEFAULT_BATCH_SIZE
) -> dict[str, int]:
    """One-time migration: compute and store an embedding for every existing
    canonical entity that doesn't have one yet, so incremental resolve
    (fetch_existing_clusters above) has the *whole* corpus as context, not
    just whatever's been merged since this feature shipped. Safe to re-run
    -- only ever touches nodes entities_missing_embedding_query() returns,
    so a second run is a fast no-op once nothing is missing.

    Embeds each entity's display `name` (not raw mentions -- there's no
    per-mention text to re-derive at this point, only the canonical name
    already chosen), with the same model/normalization
    src.extraction.resolve.cluster_names() uses, so the vectors are directly
    comparable to ones computed there.
    """
    counts: dict[str, int] = {}
    for entity_type in ENTITY_LABELS:
        records, _, _ = driver.execute_query(
            entities_missing_embedding_query(entity_type), database_=database, routing_="r"
        )
        rows = [record.data() for record in records]
        if not rows:
            counts[entity_type] = 0
            continue

        names = [row["name"] for row in rows]
        embeddings = model.encode(names, normalize_embeddings=True, show_progress_bar=False)

        update_rows = [
            {"normalized_name": rows[index]["normalized_name"], "embedding": embeddings[index].tolist()}
            for index in range(len(rows))
        ]
        for batch in _chunks(update_rows, batch_size):
            driver.execute_query(set_entity_embeddings_query(entity_type), rows=batch, database_=database)

        counts[entity_type] = len(rows)
        logger.info("%s: backfilled embedding for %d entit(y/ies)", entity_type, len(rows))

    return counts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Merge resolved (paper, entity) rows into Neo4j as "
        "Method/Dataset/ResearchTopic nodes and relationships."
    )
    parser.add_argument("resolved_path", type=Path, help="Resolved JSONL from src.extraction.resolve")
    parser.add_argument(
        "--batch-size", type=int, default=DEFAULT_BATCH_SIZE,
        help="Rows per Neo4j transaction (default: %(default)s)",
    )
    parser.add_argument("--log-level", default="INFO", help="Logging level (default: %(default)s)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(message)s")

    rows = read_resolved(args.resolved_path)
    driver = get_driver()
    try:
        entities_written, relations_written = merge_resolved(
            driver, NEO4J_DATABASE, rows, batch_size=args.batch_size
        )
    finally:
        driver.close()

    logger.info(
        "Merged %d entity upsert(s), %d relationship upsert(s) from %s",
        entities_written, relations_written, args.resolved_path,
    )


if __name__ == "__main__":
    main()
