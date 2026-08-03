import argparse
import logging
from pathlib import Path

from neo4j import Driver

from src.config import NEO4J_DATABASE, get_driver

logger = logging.getLogger(__name__)

CYPHER_DIR = Path(__file__).parents[2] / "cypher"
SCHEMA_FILES = [CYPHER_DIR / "constrains.cypher", CYPHER_DIR / "index.cypher"]


def _statements(cypher_path: Path) -> list[str]:
    text = cypher_path.read_text(encoding="utf-8")
    return [stmt.strip() for stmt in text.split(";") if stmt.strip()]


def apply_schema(driver: Driver, database: str | None = NEO4J_DATABASE) -> None:
    """Apply every constraint/index statement in cypher/*.cypher. Safe to rerun —
    every statement is `IF NOT EXISTS`, so this is meant to run on every pipeline
    invocation rather than once by hand."""
    for cypher_path in SCHEMA_FILES:
        for statement in _statements(cypher_path):
            _, summary, _ = driver.execute_query(statement, database_=database)
            counters = summary.counters
            label = statement.splitlines()[0]
            if counters.constraints_added or counters.indexes_added:
                logger.info("Created: %s", label)
            else:
                logger.info("Already exists: %s", label)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply Neo4j constraints and indexes (idempotent)."
    )
    parser.add_argument(
        "--log-level", default="INFO", help="Logging level (default: %(default)s)"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=args.log_level, format="%(asctime)s %(levelname)s %(message)s"
    )

    driver = get_driver()
    try:
        apply_schema(driver)
        logger.info("Schema applied.")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
