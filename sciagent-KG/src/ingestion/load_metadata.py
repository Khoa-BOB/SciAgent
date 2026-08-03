import argparse
import json
import logging
from pathlib import Path
from typing import Any, Iterable

from neo4j import Driver, Transaction

from queries.metadata import UPSERT_PAPER
from src.check_connection import check_connection
from src.config import NEO4J_DATABASE, get_driver
from src.ingestion.checkpoint import load_checkpoint, reset_checkpoint, save_checkpoint
from src.ingestion.transform import transform

logger = logging.getLogger(__name__)

DEFAULT_METADATA_PATH = Path(__file__).parents[3] / "data/example/mock_500.jsonl"
DEFAULT_BATCH_SIZE = 50


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


def _upsert_batch(tx: Transaction, payloads: list[dict[str, Any]]) -> None:
    for payload in payloads:
        tx.run(UPSERT_PAPER, **payload)


def load_metadata(
    metadata_path: Path,
    neo4j_driver: Driver,
    database: str | None = NEO4J_DATABASE,
    batch_size: int = DEFAULT_BATCH_SIZE,
    resume: bool = True,
) -> int:
    """Transform and upsert metadata records in batches, returning the loaded count.

    Progress is checkpointed after every successfully committed batch, so a run
    interrupted partway through can resume from the last good batch instead of
    reprocessing the whole file (`resume=True`, the default).
    """
    start_after = 0
    if resume:
        checkpoint = load_checkpoint(metadata_path)
        if checkpoint is not None:
            start_after = checkpoint.last_line
            logger.info(
                "Resuming %s after line %d (last loaded: %s)",
                metadata_path,
                start_after,
                checkpoint.last_arxiv_id,
            )

    loaded_count = 0
    pending: list[tuple[int, dict[str, Any]]] = []

    def flush() -> None:
        nonlocal loaded_count, pending
        if not pending:
            return

        line_numbers = [line_number for line_number, _ in pending]
        payloads = [payload for _, payload in pending]

        try:
            with neo4j_driver.session(database=database) as session:
                session.execute_write(_upsert_batch, payloads)
        except Exception as error:
            raise RuntimeError(
                f"Failed to load {metadata_path} on lines "
                f"{line_numbers[0]}-{line_numbers[-1]}"
            ) from error

        loaded_count += len(pending)
        save_checkpoint(metadata_path, line_numbers[-1], payloads[-1]["arxiv_id"])
        logger.info(
            "Loaded %d paper(s) so far (batch: lines %d-%d, up to %s)",
            loaded_count,
            line_numbers[0],
            line_numbers[-1],
            payloads[-1]["arxiv_id"],
        )
        pending = []

    for line_number, record in read_metadata(metadata_path):
        if line_number <= start_after:
            continue

        try:
            payload = transform(record)
        except Exception as error:
            raise RuntimeError(
                f"Failed to transform {metadata_path} on line {line_number}"
            ) from error

        pending.append((line_number, payload))
        if len(pending) >= batch_size:
            flush()

    flush()

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
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="Number of papers committed per Neo4j transaction (default: %(default)s)",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Ignore any existing checkpoint and reprocess the whole file.",
    )
    parser.add_argument(
        "--reset-checkpoint",
        action="store_true",
        help="Delete the checkpoint for this file before loading.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (default: %(default)s)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=args.log_level, format="%(asctime)s %(levelname)s %(message)s"
    )

    if args.reset_checkpoint:
        reset_checkpoint(args.metadata_path)

    driver = get_driver()
    try:
        if not check_connection(driver):
            raise ConnectionError("Could not connect to Neo4j")

        logger.info("Connection successful")
        loaded_count = load_metadata(
            args.metadata_path,
            driver,
            batch_size=args.batch_size,
            resume=not args.no_resume,
        )
        logger.info("Loaded %d paper(s)", loaded_count)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
