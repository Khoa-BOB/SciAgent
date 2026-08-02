import argparse
import json
from pathlib import Path
from typing import Any, Iterable

from neo4j import Driver

from queries.metadata import UPSERT_PAPER
from src.check_connection import check_connection, driver
from src.config import NEO4J_DATABASE
from src.transform import transform


DEFAULT_METADATA_PATH = Path(__file__).parents[2] / "data/example/mock_500.jsonl"


def read_metadata(metadata_path: Path) -> Iterable[tuple[int, dict[str, Any]]]:
    """Yield non-empty JSONL records together with their source line number."""
    with metadata_path.open(encoding="utf-8") as metadata_file:
        for line_number, line in enumerate(metadata_file, start=1):
            if not line.strip():
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"Invalid JSON in {metadata_path} on line {line_number}"
                ) from error

            if not isinstance(record, dict):
                raise ValueError(
                    f"Expected a JSON object in {metadata_path} "
                    f"on line {line_number}"
                )

            yield line_number, record


def load_metadata(
    metadata_path: Path,
    neo4j_driver: Driver = driver,
    database: str | None = NEO4J_DATABASE,
) -> int:
    """Transform and upsert every metadata record, returning the loaded count."""
    loaded_count = 0

    for line_number, record in read_metadata(metadata_path):
        try:
            payload = transform(record)
            neo4j_driver.execute_query(
                UPSERT_PAPER,
                parameters_=payload,
                database_=database,
            )
        except Exception as error:
            raise RuntimeError(
                f"Failed to load {metadata_path} on line {line_number}"
            ) from error

        loaded_count += 1
        print(f"Loaded paper {payload['arxiv_id']}")

    return loaded_count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load arXiv metadata into Neo4j.")
    parser.add_argument(
        "metadata_path",
        nargs="?",
        type=Path,
        default=DEFAULT_METADATA_PATH,
        help=f"JSONL metadata file (default: {DEFAULT_METADATA_PATH})",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    try:
        if not check_connection():
            raise ConnectionError("Could not connect to Neo4j")

        print("Connection successful")
        loaded_count = load_metadata(args.metadata_path)
        print(f"Loaded {loaded_count} paper(s)")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
