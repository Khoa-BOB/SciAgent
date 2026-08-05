"""Stage C: collapse near-duplicate extracted entity names (e.g. "CNN" /
"CNNs" / "convolutional neural network") into one canonical entity per
underlying concept, before anything gets written to Neo4j.

Reuses the same embedding model the retrieval pipeline already runs, so
resolution doesn't pull in a new model dependency.
"""

import argparse
import json
import logging
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

from src.ingestion.embeddings.index_papers import MODEL_NAME

logger = logging.getLogger(__name__)

DEFAULT_SIMILARITY_THRESHOLD = 0.85


@dataclass
class RawMention:
    paper_id: str
    entity_type: str
    name: str
    extraction_model: str
    extracted_at: str


def load_extractions(shards_dir: Path) -> list[RawMention]:
    mentions = []
    for path in sorted(shards_dir.glob("*.extracted.jsonl")):
        with path.open(encoding="utf-8") as extracted_file:
            for line in extracted_file:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                for entity in record["entities"]:
                    mentions.append(
                        RawMention(
                            paper_id=record["paper_id"],
                            entity_type=entity["type"],
                            name=entity["name"].strip(),
                            extraction_model=record["extraction_model"],
                            extracted_at=record["extracted_at"],
                        )
                    )
    return mentions


def _normalize(name: str) -> str:
    return " ".join(name.lower().split())


def cluster_names(
    names: list[str], model: SentenceTransformer, threshold: float
) -> dict[str, str]:
    """Greedy nearest-cluster merge: names are processed most-frequent-first
    (so common phrasing claims the canonical slot), and each subsequent name
    joins the most similar existing cluster if cosine similarity clears
    `threshold`, else starts a new one. O(n * clusters) -- fine at the scale
    of unique entity names (hundreds to low thousands), not paper count.
    """
    if not names:
        return {}

    embeddings = model.encode(names, normalize_embeddings=True, show_progress_bar=False)

    canonical_names: list[str] = []
    canonical_embeddings: list[np.ndarray] = []
    mapping: dict[str, str] = {}

    for name, embedding in zip(names, embeddings):
        if canonical_embeddings:
            similarities = np.dot(np.vstack(canonical_embeddings), embedding)
            best_index = int(np.argmax(similarities))
            if similarities[best_index] >= threshold:
                mapping[name] = canonical_names[best_index]
                continue

        canonical_names.append(name)
        canonical_embeddings.append(embedding)
        mapping[name] = name

    return mapping


def resolve(shards_dir: Path, threshold: float = DEFAULT_SIMILARITY_THRESHOLD) -> list[dict]:
    mentions = load_extractions(shards_dir)
    if not mentions:
        return []

    model = SentenceTransformer(MODEL_NAME)

    by_type: dict[str, list[RawMention]] = defaultdict(list)
    for mention in mentions:
        by_type[mention.entity_type].append(mention)

    resolved_rows: list[dict] = []
    for entity_type, type_mentions in by_type.items():
        counts = Counter(m.name for m in type_mentions)
        unique_names = [name for name, _ in counts.most_common()]  # most frequent first
        mapping = cluster_names(unique_names, model, threshold)

        logger.info(
            "%s: %d mention(s), %d unique name(s) -> %d canonical entit(y/ies)",
            entity_type, len(type_mentions), len(unique_names), len(set(mapping.values())),
        )

        for mention in type_mentions:
            canonical = mapping[mention.name]
            resolved_rows.append(
                {
                    "paper_id": mention.paper_id,
                    "entity_type": entity_type,
                    "name": canonical,
                    "normalized_name": _normalize(canonical),
                    "extraction_model": mention.extraction_model,
                    "extracted_at": mention.extracted_at,
                }
            )

    return resolved_rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Resolve near-duplicate extracted entity names into "
        "canonical entities via embedding-similarity clustering."
    )
    parser.add_argument(
        "shards_dir", type=Path,
        help="Directory of *.extracted.jsonl files (from src.extraction.extract)",
    )
    parser.add_argument("--output", type=Path, required=True, help="Output resolved JSONL path")
    parser.add_argument(
        "--threshold", type=float, default=DEFAULT_SIMILARITY_THRESHOLD,
        help="Cosine similarity threshold to merge into an existing cluster (default: %(default)s)",
    )
    parser.add_argument("--log-level", default="INFO", help="Logging level (default: %(default)s)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(message)s")

    rows = resolve(args.shards_dir, threshold=args.threshold)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as output_file:
        for row in rows:
            output_file.write(json.dumps(row, ensure_ascii=False) + "\n")

    logger.info("Wrote %d resolved (paper, entity) row(s) to %s", len(rows), args.output)


if __name__ == "__main__":
    main()
