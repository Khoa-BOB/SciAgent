import argparse
import logging
from pathlib import Path

from neo4j import Driver
from neo4j.exceptions import ServiceUnavailable
from sentence_transformers import SentenceTransformer

from src.check_connection import check_connection
from src.config import get_driver
from src.ingestion.checkpoint import reset_checkpoint
from src.ingestion.embeddings.index_papers import BATCH_SIZE as EMBED_BATCH_SIZE
from src.ingestion.embeddings.index_papers import MODEL_NAME as EMBED_MODEL_NAME
from src.ingestion.embeddings.index_papers import run_embedding
from src.ingestion.load_metadata import DEFAULT_BATCH_SIZE as LOAD_BATCH_SIZE
from src.ingestion.load_metadata import DEFAULT_METADATA_PATH, load_metadata
from src.ingestion.retry import with_retry
from src.ingestion.schema import apply_schema
from src.ingestion.validate import print_report, run_validation

logger = logging.getLogger(__name__)


def cmd_schema(driver: Driver, args: argparse.Namespace) -> None:
    apply_schema(driver)
    logger.info("Schema applied.")


def cmd_load(driver: Driver, args: argparse.Namespace) -> None:
    if args.reset_checkpoint:
        reset_checkpoint(args.metadata_path)
    loaded = load_metadata(
        args.metadata_path,
        driver,
        batch_size=args.batch_size,
        resume=not args.no_resume,
    )
    logger.info("Loaded %d paper(s).", loaded)


def cmd_embed(driver: Driver, args: argparse.Namespace) -> None:
    model = SentenceTransformer(args.model)
    total = run_embedding(
        driver,
        model,
        limit=args.limit,
        batch_size=args.batch_size,
        property_name=args.property,
        model_name=args.model,
        prompt_name=args.prompt_name or None,
        only_missing=not args.reembed_all,
        dry_run=args.dry_run,
    )
    logger.info("Embedded %d paper(s) total.", total)


def cmd_validate(driver: Driver, args: argparse.Namespace) -> None:
    results = run_validation(driver)
    all_passed = print_report(results)
    if not all_passed:
        raise SystemExit(1)


def cmd_all(driver: Driver, args: argparse.Namespace) -> None:
    """Convenience: schema -> load -> embed -> validate, using each stage's defaults."""
    if args.reset_checkpoint:
        reset_checkpoint(args.metadata_path)

    cmd_schema(driver, args)

    loaded = load_metadata(args.metadata_path, driver, resume=not args.no_resume)
    logger.info("Loaded %d paper(s).", loaded)

    model = SentenceTransformer(EMBED_MODEL_NAME)
    total = run_embedding(driver, model, batch_size=EMBED_BATCH_SIZE)
    logger.info("Embedded %d paper(s) total.", total)

    results = run_validation(driver)
    all_passed = print_report(results)
    if not all_passed:
        raise SystemExit(1)


def _add_load_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "metadata_path",
        nargs="?",
        type=Path,
        default=DEFAULT_METADATA_PATH,
        help=f"JSONL metadata file (default: {DEFAULT_METADATA_PATH})",
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SciAgent KG ingestion pipeline.")
    parser.add_argument(
        "--log-level", default="INFO", help="Logging level (default: %(default)s)"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("schema", help="Apply Neo4j constraints and indexes.")

    load_parser = subparsers.add_parser(
        "load", help="Load a JSONL metadata file into Neo4j."
    )
    _add_load_args(load_parser)
    load_parser.add_argument(
        "--batch-size",
        type=int,
        default=LOAD_BATCH_SIZE,
        help="Papers committed per Neo4j transaction (default: %(default)s)",
    )

    embed_parser = subparsers.add_parser(
        "embed", help="Embed papers and store vectors."
    )
    embed_parser.add_argument(
        "--limit", type=int, default=None, help="Only embed the first N eligible papers."
    )
    embed_parser.add_argument(
        "--batch-size",
        type=int,
        default=EMBED_BATCH_SIZE,
        help="Papers fetched from Neo4j and embedded per batch (default: %(default)s)",
    )
    embed_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute embeddings but don't write them to Neo4j.",
    )
    embed_parser.add_argument(
        "--model",
        default=EMBED_MODEL_NAME,
        help="SentenceTransformer model (default: %(default)s)",
    )
    embed_parser.add_argument(
        "--property",
        default="embedding",
        help="Paper property to write embeddings to (default: %(default)s)",
    )
    embed_parser.add_argument(
        "--prompt-name",
        default="document",
        help="Prompt name for model.encode() (default: %(default)s)",
    )
    embed_parser.add_argument(
        "--reembed-all",
        action="store_true",
        help="Recompute embeddings for every eligible paper.",
    )

    subparsers.add_parser("validate", help="Run post-load sanity checks.")

    all_parser = subparsers.add_parser(
        "all",
        help="Run schema, load, embed, validate in sequence (default batch sizes).",
    )
    _add_load_args(all_parser)

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=args.log_level, format="%(asctime)s %(levelname)s %(message)s"
    )
    # The neo4j driver already retries transient errors internally; surface that
    # activity instead of staying silent about it.
    logging.getLogger("neo4j").setLevel(logging.WARNING)

    driver = get_driver()
    try:
        with_retry(
            driver.verify_connectivity,
            retries=5,
            base_delay=1.0,
            retryable=(ServiceUnavailable,),
        )
        if not check_connection(driver):
            raise ConnectionError("Could not connect to Neo4j")

        commands = {
            "schema": cmd_schema,
            "load": cmd_load,
            "embed": cmd_embed,
            "validate": cmd_validate,
            "all": cmd_all,
        }
        commands[args.command](driver, args)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
