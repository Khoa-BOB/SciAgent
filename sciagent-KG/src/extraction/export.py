import argparse
import json
import logging
from pathlib import Path

from neo4j import Driver

from src.config import NEO4J_DATABASE, get_driver

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR = Path(__file__).parents[3] / "data/extraction/shards"
DEFAULT_SHARD_SIZE = 1000


def export_papers(
    driver: Driver, database: str | None, limit: int | None = None
) -> list[dict]:
    """Pull (arxiv_id, title, abstract) for every extraction-eligible paper.

    Compute nodes on an HPC cluster generally can't reach a Neo4j instance
    running on a dev machine, so extraction runs offline against a flat
    export instead of querying the graph live.
    """
    query = """
        MATCH (p:Paper)
        WHERE p.title IS NOT NULL AND p.abstract IS NOT NULL AND trim(p.abstract) <> ""
        RETURN p.arxiv_id AS arxiv_id, p.title AS title, p.abstract AS abstract
        ORDER BY p.arxiv_id
    """ + ("LIMIT $limit" if limit is not None else "")

    records, _, _ = driver.execute_query(
        query, limit=limit, database_=database, routing_="r"
    )
    return [record.data() for record in records]


def write_shards(papers: list[dict], output_dir: Path, shard_size: int) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    shard_paths = []
    for start in range(0, len(papers), shard_size):
        shard = papers[start : start + shard_size]
        shard_path = output_dir / f"shard_{start // shard_size:04d}.jsonl"
        with shard_path.open("w", encoding="utf-8") as shard_file:
            for paper in shard:
                shard_file.write(json.dumps(paper, ensure_ascii=False) + "\n")
        shard_paths.append(shard_path)
    return shard_paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export (arxiv_id, title, abstract) from Neo4j into JSONL "
        "shards for offline entity extraction (e.g. on an HPC cluster)."
    )
    parser.add_argument(
        "--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR,
        help=f"Directory to write shard_NNNN.jsonl files into (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--shard-size", type=int, default=DEFAULT_SHARD_SIZE,
        help="Papers per shard, i.e. per SLURM array task (default: %(default)s)",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Only export the first N eligible papers (for a pilot run).",
    )
    parser.add_argument("--log-level", default="INFO", help="Logging level (default: %(default)s)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(message)s")

    driver = get_driver()
    try:
        papers = export_papers(driver, NEO4J_DATABASE, limit=args.limit)
    finally:
        driver.close()

    shard_paths = write_shards(papers, args.output_dir, args.shard_size)
    logger.info(
        "Exported %d paper(s) into %d shard(s) under %s",
        len(papers), len(shard_paths), args.output_dir,
    )


if __name__ == "__main__":
    main()
