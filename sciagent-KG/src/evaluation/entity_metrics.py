"""Two benchmarks for the domain-entity layer (Method/Dataset/ResearchTopic),
distinct from src/evaluation/metrics.py which measures paper *retrieval*
(a different question entirely -- see docs).

1. Extraction quality: precision/recall/F1 per entity type against
   eval/entity_extraction_ground_truth.jsonl -- a hand-labeled sample built
   by reading each paper's title+abstract directly (not by re-running the
   LLM or any automated heuristic), so it's an independent check, not a
   self-grading loop.

2. Resolution quality: for a curated list of name pairs known to refer to
   the same (or, for negative controls, different) real-world concepts,
   checks whether they actually ended up as the same canonical entity in
   Neo4j -- a direct measurement of the merge-rate gap noted in
   docs/entity_extraction_pipeline.md's Known Limitations.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from neo4j import Driver

ENTITY_TYPES = ("method", "dataset", "topic")

GROUND_TRUTH_PATH = Path(__file__).parents[2] / "eval/entity_extraction_ground_truth.jsonl"


@dataclass
class TypeScore:
    entity_type: str
    tp: int
    fp: int
    fn: int

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if (self.tp + self.fp) else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if (self.tp + self.fn) else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0


def load_ground_truth(path: Path = GROUND_TRUTH_PATH) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as gt_file:
        for line in gt_file:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def score_extraction(rows: list[dict]) -> dict[str, TypeScore]:
    """Aggregate the per-paper (tp, fp, fn) judgments in the ground truth
    file into one score per entity type, plus an overall micro-average."""
    totals = {t: [0, 0, 0] for t in ENTITY_TYPES}
    for row in rows:
        for entity_type in ENTITY_TYPES:
            tp, fp, fn = row[entity_type]
            totals[entity_type][0] += tp
            totals[entity_type][1] += fp
            totals[entity_type][2] += fn

    scores = {t: TypeScore(t, *totals[t]) for t in ENTITY_TYPES}
    overall_tp = sum(s.tp for s in scores.values())
    overall_fp = sum(s.fp for s in scores.values())
    overall_fn = sum(s.fn for s in scores.values())
    scores["overall"] = TypeScore("overall", overall_tp, overall_fp, overall_fn)
    return scores


# Curated (name_a, name_b, entity_type, should_merge) pairs -- a mix of known
# synonyms/abbreviation-expansion pairs (should_merge=True) and superficially
# similar but genuinely distinct concepts (should_merge=False, a check
# against over-merging). Only pairs where BOTH names are known to exist
# somewhere in the corpus are meaningful; check_resolution() skips any pair
# where either name isn't found.
SYNONYM_PAIRS: list[tuple[str, str, str, bool]] = [
    ("CNN", "convolutional neural network", "method", True),
    ("GNN", "graph neural network", "method", True),
    ("GAN", "generative adversarial network", "method", True),
    ("SVM", "support vector machine", "method", True),
    ("LLM", "large language model", "method", True),
    ("RL", "reinforcement learning", "method", True),
    ("BNN", "Bayesian Neural Network", "method", True),
    ("RNN", "recurrent neural network", "method", True),
    ("NLP", "natural language processing", "topic", True),
    ("FORC", "first-order reversal curve", "method", True),
    ("MCTS", "Monte Carlo Tree Search", "method", True),
    # Negative controls -- related but genuinely distinct; merging these
    # would be a false-merge / over-clustering error.
    ("CNN", "RNN", "method", False),
    ("supervised learning", "reinforcement learning", "method", False),
    ("CIFAR-10", "CIFAR-100", "dataset", False),
    ("GAN", "VAE", "method", False),
]


@dataclass
class ResolutionCase:
    name_a: str
    name_b: str
    entity_type: str
    should_merge: bool
    both_present: bool
    merged: bool


@dataclass
class ResolutionScore:
    cases: list[ResolutionCase]

    @property
    def evaluable(self) -> list[ResolutionCase]:
        return [c for c in self.cases if c.both_present]

    @property
    def merge_recall(self) -> float:
        """Of known-synonym pairs where both names appear in the corpus,
        what fraction actually ended up as the same canonical entity."""
        positives = [c for c in self.evaluable if c.should_merge]
        if not positives:
            return 0.0
        return sum(c.merged for c in positives) / len(positives)

    @property
    def merge_precision(self) -> float:
        """Of negative-control pairs where both names appear, what fraction
        correctly stayed separate (1.0 - false-merge rate)."""
        negatives = [c for c in self.evaluable if not c.should_merge]
        if not negatives:
            return 1.0
        return 1 - sum(c.merged for c in negatives) / len(negatives)


LABELS = {"method": "Method", "dataset": "Dataset", "topic": "ResearchTopic"}


def check_resolution(
    driver: Driver, database: str | None, pairs: list[tuple[str, str, str, bool]] = SYNONYM_PAIRS
) -> ResolutionScore:
    cases = []
    for name_a, name_b, entity_type, should_merge in pairs:
        label = LABELS[entity_type]
        records, _, _ = driver.execute_query(
            f"""
            OPTIONAL MATCH (a:{label}) WHERE toLower(a.name) = toLower($name_a)
            OPTIONAL MATCH (b:{label}) WHERE toLower(b.name) = toLower($name_b)
            RETURN a.normalized_name AS a_canonical, b.normalized_name AS b_canonical
            """,
            name_a=name_a, name_b=name_b, database_=database,
        )
        a_canonical = records[0]["a_canonical"] if records else None
        b_canonical = records[0]["b_canonical"] if records else None
        both_present = a_canonical is not None and b_canonical is not None
        merged = both_present and a_canonical == b_canonical
        cases.append(ResolutionCase(name_a, name_b, entity_type, should_merge, both_present, merged))
    return ResolutionScore(cases)
