"""Orchestrates the full local domain-KG extraction pipeline sequentially:
export -> (spaCy + LLM) extract -> resolve -> merge.

On HPC, the stages are driven separately instead (see shell_script/hpc/):
`export` runs once locally, `extract` runs as a SLURM array job (one shard
per task, in parallel, each against its own vLLM server), then `resolve`
and `merge` run back on the machine hosting Neo4j.
"""

import argparse
import json
import logging
from pathlib import Path

from src.config import NEO4J_DATABASE, get_driver
from src.extraction.candidates import DEFAULT_SPACY_MODEL
from src.extraction.export import DEFAULT_OUTPUT_DIR as DEFAULT_SHARDS_DIR
from src.extraction.export import DEFAULT_SHARD_SIZE, export_papers, write_shards
from src.extraction.extract import DEFAULT_BASE_URL, DEFAULT_MODEL, run_extraction
from src.extraction.llm_client import ExtractionClient
from src.extraction.merge import merge_resolved, read_resolved
from src.extraction.resolve import DEFAULT_SIMILARITY_THRESHOLD, resolve
from src.ingestion.schema import apply_schema

logger = logging.getLogger(__name__)

DEFAULT_RESOLVED_PATH = Path(__file__).parents[2] / "data/extraction/resolved.jsonl"


def cmd_schema(args: argparse.Namespace) -> None:
    driver = get_driver()
    try:
        apply_schema(driver)
    finally:
        driver.close()
    logger.info("Schema applied (includes Method/Dataset/ResearchTopic constraints).")


def cmd_export(args: argparse.Namespace) -> None:
    driver = get_driver()
    try:
        papers = export_papers(driver, NEO4J_DATABASE, limit=args.limit)
    finally:
        driver.close()
    shard_paths = write_shards(papers, args.output_dir, args.shard_size)
    logger.info("Exported %d paper(s) into %d shard(s) under %s", len(papers), len(shard_paths), args.output_dir)


def cmd_extract(args: argparse.Namespace) -> None:
    shard_paths = sorted(args.shards_dir.glob("shard_*.jsonl"))
    if not shard_paths:
        logger.warning("No shard_*.jsonl files found in %s -- run 'export' first.", args.shards_dir)
        return

    client = ExtractionClient(base_url=args.base_url, model=args.model, api_key=args.api_key)
    total = 0
    for shard_path in shard_paths:
        output_path = shard_path.with_suffix(".extracted.jsonl")
        processed = run_extraction(
            shard_path, output_path, client,
            spacy_model=args.spacy_model, resume=not args.no_resume,
        )
        total += processed
        logger.info("%s: extracted %d paper(s)", shard_path.name, processed)
    logger.info("Extraction complete: %d paper(s) across %d shard(s)", total, len(shard_paths))


def cmd_resolve(args: argparse.Namespace) -> None:
    rows = resolve(args.shards_dir, threshold=args.threshold)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as output_file:
        for row in rows:
            output_file.write(json.dumps(row, ensure_ascii=False) + "\n")
    logger.info("Resolved %d (paper, entity) row(s) into %s", len(rows), args.output)


def cmd_merge(args: argparse.Namespace) -> None:
    rows = read_resolved(args.resolved_path)
    driver = get_driver()
    try:
        entities_written, relations_written = merge_resolved(
            driver, NEO4J_DATABASE, rows, batch_size=args.batch_size
        )
    finally:
        driver.close()
    logger.info(
        "Merged %d entity upsert(s), %d relationship upsert(s)",
        entities_written, relations_written,
    )


def cmd_all(args: argparse.Namespace) -> None:
    cmd_schema(args)
    cmd_export(args)
    cmd_extract(args)
    cmd_resolve(args)
    cmd_merge(args)


def _add_common_llm_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="OpenAI-compatible API base URL (default: %(default)s, i.e. local Ollama)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model name as served by the backend (default: %(default)s)")
    parser.add_argument("--api-key", default="not-needed", help="API key, if the backend requires one")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Domain KG extraction pipeline: export -> spaCy+LLM extract -> resolve -> merge."
    )
    parser.add_argument("--log-level", default="INFO", help="Logging level (default: %(default)s)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("schema", help="Apply Method/Dataset/ResearchTopic constraints (and everything else in cypher/).")

    export_parser = subparsers.add_parser("export", help="Export papers from Neo4j into shard JSONL files.")
    export_parser.add_argument("--output-dir", type=Path, default=DEFAULT_SHARDS_DIR)
    export_parser.add_argument("--shard-size", type=int, default=DEFAULT_SHARD_SIZE)
    export_parser.add_argument("--limit", type=int, default=None, help="Only export the first N papers (pilot run).")

    extract_parser = subparsers.add_parser("extract", help="Run spaCy+LLM extraction over every shard in a directory, sequentially.")
    extract_parser.add_argument("--shards-dir", type=Path, default=DEFAULT_SHARDS_DIR)
    extract_parser.add_argument("--spacy-model", default=DEFAULT_SPACY_MODEL)
    extract_parser.add_argument("--no-resume", action="store_true")
    _add_common_llm_args(extract_parser)

    resolve_parser = subparsers.add_parser("resolve", help="Cluster extracted entity names into canonical entities.")
    resolve_parser.add_argument("--shards-dir", type=Path, default=DEFAULT_SHARDS_DIR)
    resolve_parser.add_argument("--output", type=Path, default=DEFAULT_RESOLVED_PATH)
    resolve_parser.add_argument("--threshold", type=float, default=DEFAULT_SIMILARITY_THRESHOLD)

    merge_parser = subparsers.add_parser("merge", help="Merge resolved entities/relationships into Neo4j.")
    merge_parser.add_argument("--resolved-path", type=Path, default=DEFAULT_RESOLVED_PATH)
    merge_parser.add_argument("--batch-size", type=int, default=500)

    all_parser = subparsers.add_parser("all", help="Run every stage in sequence (local/pilot use -- not for HPC).")
    all_parser.add_argument("--output-dir", type=Path, default=DEFAULT_SHARDS_DIR, dest="output_dir")
    all_parser.add_argument("--shards-dir", type=Path, default=DEFAULT_SHARDS_DIR)
    all_parser.add_argument("--shard-size", type=int, default=DEFAULT_SHARD_SIZE)
    all_parser.add_argument("--limit", type=int, default=None, help="Only export/process the first N papers (pilot run).")
    all_parser.add_argument("--spacy-model", default=DEFAULT_SPACY_MODEL)
    all_parser.add_argument("--no-resume", action="store_true")
    all_parser.add_argument("--output", type=Path, default=DEFAULT_RESOLVED_PATH)
    all_parser.add_argument("--resolved-path", type=Path, default=DEFAULT_RESOLVED_PATH)
    all_parser.add_argument("--threshold", type=float, default=DEFAULT_SIMILARITY_THRESHOLD)
    all_parser.add_argument("--batch-size", type=int, default=500)
    _add_common_llm_args(all_parser)

    return parser.parse_args()


COMMANDS = {
    "schema": cmd_schema,
    "export": cmd_export,
    "extract": cmd_extract,
    "resolve": cmd_resolve,
    "merge": cmd_merge,
    "all": cmd_all,
}


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(message)s")
    COMMANDS[args.command](args)


if __name__ == "__main__":
    main()
