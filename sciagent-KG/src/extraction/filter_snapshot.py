"""Cluster-side data prep: filter a local copy of the raw arXiv OAI snapshot
down to just the papers currently in the KG, using an id list exported from
Neo4j (`src.extraction.export --ids-only`), and shard the result for a
SLURM array job.

No Neo4j access needed here -- this is what lets the whole extraction step
run entirely on the cluster, using whatever copy of the snapshot already
lives on its filesystem instead of shipping title/abstract text over the
network.
"""

import argparse
import json
import logging
from pathlib import Path

from src.extraction.export import DEFAULT_SHARD_SIZE, write_shards

logger = logging.getLogger(__name__)


def load_id_set(ids_path: Path) -> set[str]:
    with ids_path.open(encoding="utf-8") as ids_file:
        return {line.strip() for line in ids_file if line.strip()}


def filter_snapshot(snapshot_path: Path, ids_path: Path) -> list[dict]:
    wanted = load_id_set(ids_path)
    found: dict[str, dict] = {}

    with snapshot_path.open(encoding="utf-8") as snapshot_file:
        for line_number, line in enumerate(snapshot_file, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("Skipping invalid JSON on line %d", line_number)
                continue

            arxiv_id = record.get("id")
            if arxiv_id in wanted and arxiv_id not in found:
                found[arxiv_id] = {
                    "arxiv_id": arxiv_id,
                    "title": (record.get("title") or "").strip(),
                    "abstract": (record.get("abstract") or "").strip(),
                }
                if len(found) == len(wanted):
                    break  # every requested paper has been found

    missing = wanted - found.keys()
    if missing:
        logger.warning(
            "%d of %d requested paper(s) not found in %s (sample: %s)",
            len(missing), len(wanted), snapshot_path, sorted(missing)[:5],
        )

    return sorted(found.values(), key=lambda paper: paper["arxiv_id"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Filter a local arXiv snapshot down to the papers listed "
        "in --ids, and shard the result for extraction."
    )
    parser.add_argument("snapshot", type=Path, help="Path to arxiv-metadata-oai-snapshot.json on this machine")
    parser.add_argument(
        "--ids", type=Path, required=True,
        help="Flat file of arxiv_ids, one per line (from `export.py --ids-only`)",
    )
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory to write shard_NNNN.jsonl files into")
    parser.add_argument("--shard-size", type=int, default=DEFAULT_SHARD_SIZE, help="Papers per shard (default: %(default)s)")
    parser.add_argument("--log-level", default="INFO", help="Logging level (default: %(default)s)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(message)s")

    papers = filter_snapshot(args.snapshot, args.ids)
    shard_paths = write_shards(papers, args.output_dir, args.shard_size)

    logger.info(
        "Filtered %d paper(s) from %s into %d shard(s) under %s",
        len(papers), args.snapshot, len(shard_paths), args.output_dir,
    )


if __name__ == "__main__":
    main()
