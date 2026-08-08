import argparse
import json
import logging
from pathlib import Path
from typing import Iterator, TypeVar

from neo4j import Driver

from queries.entities import upsert_entities_query, upsert_relations_query
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


def _chunks(items: list[T], size: int) -> Iterator[list[T]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def merge_resolved(
    driver: Driver,
    database: str | None,
    rows: list[dict],
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> tuple[int, int]:
    """Upsert resolved (paper, entity) rows into Neo4j: one Method/Dataset/
    ResearchTopic node per unique normalized_name, one USES_METHOD/
    USES_DATASET/STUDIES_TOPIC relationship per (paper, entity) pair.

    Every write is MERGE-based, so this is safe to rerun on failure instead
    of needing its own checkpoint file -- unlike the LLM extraction stage,
    a full retry here costs nothing but some Neo4j round-trips.
    """
    by_type: dict[str, list[dict]] = {}
    for row in rows:
        by_type.setdefault(row["entity_type"], []).append(row)

    entities_written = 0
    relations_written = 0

    for entity_type, type_rows in by_type.items():
        unique_entities = list(
            {
                row["normalized_name"]: {
                    "normalized_name": row["normalized_name"],
                    "name": row["name"],
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
