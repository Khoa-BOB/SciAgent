"""Stage C: collapse near-duplicate extracted entity names (e.g. "CNN" /
"CNNs" / "convolutional neural network") into one canonical entity per
underlying concept, before anything gets written to Neo4j.

Reuses the same embedding model the retrieval pipeline already runs, so
resolution doesn't pull in a new model dependency.
"""

import argparse
import json
import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

from src.ingestion.embeddings.index_papers import MODEL_NAME

logger = logging.getLogger(__name__)

DEFAULT_SIMILARITY_THRESHOLD = 0.85

_ACRONYM_TOKEN_RE = re.compile(r"[A-Za-z]{2,6}")


def _initials(name: str) -> str:
    """Uppercase initials of each alphabetic word in a name, e.g.
    'convolutional neural network' -> 'CNN'. Only meaningful for a
    multi-word name -- callers only use it that way below."""
    words = re.findall(r"[A-Za-z]+", name)
    return "".join(word[0] for word in words).upper()


def _is_acronym_token(name: str) -> bool:
    """A short, single, all-caps word that could itself be the acronym half
    of an acronym/expansion pair -- e.g. 'CNN', 'RL', 'MCTS'."""
    stripped = name.strip()
    return bool(_ACRONYM_TOKEN_RE.fullmatch(stripped)) and stripped.isupper()


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
    names: list[str],
    model: SentenceTransformer,
    threshold: float,
    existing_clusters: list[tuple[str, np.ndarray]] | None = None,
) -> tuple[dict[str, str], dict[str, np.ndarray]]:
    """Greedy nearest-cluster merge: names are processed most-frequent-first
    (so common phrasing claims the canonical slot), and each subsequent name
    joins the most similar existing cluster if cosine similarity clears
    `threshold`, else starts a new one. O(n * clusters) comparisons -- at
    tens of thousands of unique names (real corpus scale, not the "hundreds
    to low thousands" this was first written for), clusters grows close to
    n since most names don't clear the threshold, making this effectively
    O(n^2). Embeddings are written into one preallocated array and compared
    via a sliced matmul (BLAS-backed) instead of calling np.vstack fresh
    per name -- that earlier version re-copied the entire growing array on
    every single iteration, which is what actually made this untenable at
    scale (a redundant O(n) copy on top of the O(n) comparison, per name).

    A name that fails the cosine check gets one more chance: an acronym
    fallback (see `_initials`/`_is_acronym_token`) catches acronym/expansion
    pairs whose embeddings aren't similar enough to clear `threshold` --
    e.g. "CNN" and "convolutional neural network" measured 0% merge recall
    on cosine similarity alone (see docs/entity_extraction_pipeline.md Known
    Limitations). Cosine stays the primary signal (checked first, and it's
    the stricter test) -- this is purely additive, tried only after cosine
    already failed, so it can't demote a merge cosine would have caught
    anyway. Both directions are indexed incrementally in O(1) dicts (not a
    linear rescan of every existing cluster) so this doesn't regress the
    O(n^2)-at-scale cost above: most names aren't acronym-shaped, so the
    lookup is a cheap dict miss for the common case.

    existing_clusters: optional (canonical_name, embedding) pairs already
    known -- e.g. every canonical entity already in Neo4j -- seeded into the
    cluster state *before* `names` is processed, so an incoming name can
    join one of them instead of always minting a new canonical entity from
    scratch. Embeddings must already be unit-normalized, matching what
    `model.encode(..., normalize_embeddings=True)` produces below. This is
    what makes incremental resolution (specs/02-kg-service-architecture.md
    §8.5 in sciagent-backend) full-corpus-aware without re-embedding the
    entire historical corpus on every run -- see `resolve()`'s docstring.

    Returns (mapping, new_canonical_embeddings):
    - mapping: every name in `names` -> its canonical name (which may be one
      of the seeded `existing_clusters` names).
    - new_canonical_embeddings: canonical name -> embedding, but only for
      canonical names that were *not* part of `existing_clusters` (i.e.
      created fresh in this call). Callers use this to know what actually
      needs to be persisted -- an existing cluster's embedding is already
      stored and shouldn't be touched again.
    """
    if not names:
        return {}, {}

    embeddings = model.encode(names, normalize_embeddings=True, show_progress_bar=False)

    seeds = existing_clusters or []
    canonical_names: list[str] = [name for name, _ in seeds]
    canonical_embeddings = np.empty((len(seeds) + len(names), embeddings.shape[1]), dtype=embeddings.dtype)
    for index, (_, embedding) in enumerate(seeds):
        canonical_embeddings[index] = embedding

    # acronym token (e.g. "CNN") -> cluster index, for a cluster whose
    # canonical name is itself acronym-shaped.
    acronym_to_cluster: dict[str, int] = {}
    # initials of a multi-word canonical name (e.g. "CNN", derived from
    # "convolutional neural network") -> cluster index.
    initials_to_cluster: dict[str, int] = {}

    def _index_cluster(name: str, index: int) -> None:
        if _is_acronym_token(name):
            acronym_to_cluster.setdefault(name.strip().upper(), index)
        else:
            initials = _initials(name)
            if len(initials) >= 2:
                initials_to_cluster.setdefault(initials, index)

    for index, name in enumerate(canonical_names):
        _index_cluster(name, index)

    mapping: dict[str, str] = {}
    new_canonical_embeddings: dict[str, np.ndarray] = {}
    cluster_count = len(canonical_names)

    for name, embedding in zip(names, embeddings):
        if cluster_count:
            similarities = canonical_embeddings[:cluster_count] @ embedding
            best_index = int(np.argmax(similarities))
            if similarities[best_index] >= threshold:
                mapping[name] = canonical_names[best_index]
                continue

            fallback_index = _acronym_fallback_match(
                name, acronym_to_cluster, initials_to_cluster
            )
            if fallback_index is not None:
                mapping[name] = canonical_names[fallback_index]
                continue

        canonical_names.append(name)
        canonical_embeddings[cluster_count] = embedding
        _index_cluster(name, cluster_count)
        new_canonical_embeddings[name] = embedding
        cluster_count += 1
        mapping[name] = name

    return mapping, new_canonical_embeddings


def _acronym_fallback_match(
    name: str, acronym_to_cluster: dict[str, int], initials_to_cluster: dict[str, int]
) -> int | None:
    """O(1) lookup in both directions: an acronym token joins an already-seen
    expansion's cluster, and an expansion joins an already-seen acronym
    token's cluster -- whichever form was clustered first."""
    if _is_acronym_token(name):
        return initials_to_cluster.get(name.strip().upper())

    initials = _initials(name)
    if len(initials) < 2:
        return None
    return acronym_to_cluster.get(initials)


def resolve(
    shards_dir: Path,
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    model: SentenceTransformer | None = None,
    existing_clusters: dict[str, list[tuple[str, np.ndarray]]] | None = None,
) -> tuple[list[dict], dict[str, dict[str, np.ndarray]]]:
    """Cluster every raw entity mention under `shards_dir` into canonical
    entities, per type.

    model: reuse an already-loaded SentenceTransformer instead of loading a
    fresh one -- matters when this is called once per (small) incremental
    job rather than once per (large) full-corpus run, where model load time
    would otherwise dominate. Loads MODEL_NAME itself if not given.

    existing_clusters: optional, per entity_type -> list of (canonical_name,
    embedding) pairs already in Neo4j (see merge.fetch_existing_clusters),
    seeded into that type's clustering so a new mention can join an
    already-existing canonical entity instead of only ever comparing against
    other mentions in `shards_dir`. This is what makes an incremental
    resolve (a handful of new papers) still have full-corpus context without
    re-embedding/re-clustering everything that's already in the graph -- see
    sciagent-backend/specs/02-kg-service-architecture.md §8.5. Omit for the
    original full-corpus-from-scratch behavior (the CLI's default).

    Returns (resolved_rows, new_embeddings_by_type) -- the second element is
    entity_type -> {canonical_name: embedding} for canonical entities that
    are new in this run (not part of `existing_clusters`), for merge.py to
    persist. See cluster_names()'s docstring for exactly what "new" means.
    """
    mentions = load_extractions(shards_dir)
    if not mentions:
        return [], {}

    model = model or SentenceTransformer(MODEL_NAME)

    by_type: dict[str, list[RawMention]] = defaultdict(list)
    for mention in mentions:
        by_type[mention.entity_type].append(mention)

    resolved_rows: list[dict] = []
    new_embeddings_by_type: dict[str, dict[str, np.ndarray]] = {}
    for entity_type, type_mentions in by_type.items():
        counts = Counter(m.name for m in type_mentions)
        unique_names = [name for name, _ in counts.most_common()]  # most frequent first
        type_existing = (existing_clusters or {}).get(entity_type)
        mapping, new_embeddings = cluster_names(unique_names, model, threshold, existing_clusters=type_existing)
        new_embeddings_by_type[entity_type] = new_embeddings

        logger.info(
            "%s: %d mention(s), %d unique name(s) -> %d canonical entit(y/ies) (%d new)",
            entity_type, len(type_mentions), len(unique_names), len(set(mapping.values())), len(new_embeddings),
        )

        for mention in type_mentions:
            canonical = mapping[mention.name]
            resolved_rows.append(
                {
                    "paper_id": mention.paper_id,
                    "entity_type": entity_type,
                    "name": canonical,
                    "normalized_name": _normalize(canonical),
                    # The pre-clustering name exactly as the LLM wrote it,
                    # kept even when a merge made it differ from `canonical`
                    # -- otherwise that mapping only ever exists in memory
                    # during this one run. Carried through to the relationship
                    # itself in merge.py so it survives in Neo4j independent
                    # of the *.extracted.jsonl source files.
                    "raw_name": mention.name,
                    "extraction_model": mention.extraction_model,
                    "extracted_at": mention.extracted_at,
                }
            )

    # Re-key new_canonical_embeddings by normalized_name -- merge.py's write
    # path (and Neo4j's MERGE key) is normalized_name, not the display name.
    new_embeddings_by_type = {
        entity_type: {_normalize(name): embedding for name, embedding in embeddings.items()}
        for entity_type, embeddings in new_embeddings_by_type.items()
    }

    return resolved_rows, new_embeddings_by_type


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
    """Standalone entrypoint -- `src.extraction.cli resolve` is the
    documented way to run this stage (see docs/entity_extraction_pipeline.md)
    and also persists new canonical embeddings; this one doesn't."""
    args = parse_args()
    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(message)s")

    rows, _new_embeddings = resolve(args.shards_dir, threshold=args.threshold)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as output_file:
        for row in rows:
            output_file.write(json.dumps(row, ensure_ascii=False) + "\n")

    logger.info("Wrote %d resolved (paper, entity) row(s) to %s", len(rows), args.output)


if __name__ == "__main__":
    main()
