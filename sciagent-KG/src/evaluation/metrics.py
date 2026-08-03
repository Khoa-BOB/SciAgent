from dataclasses import dataclass


def reciprocal_rank(ranked_ids: list[str], expected_id: str) -> float:
    for position, paper_id in enumerate(ranked_ids, start=1):
        if paper_id == expected_id:
            return 1.0 / position
    return 0.0


def hit_at_k(ranked_ids: list[str], expected_id: str, k: int) -> bool:
    return expected_id in ranked_ids[:k]


@dataclass
class QueryResult:
    query: str
    expected_paper_id: str
    source: str
    ranked_ids: list[str]


@dataclass
class EvalSummary:
    count: int
    mrr: float
    recall_at: dict[int, float]


def summarize(
    results: list[QueryResult], k_values: tuple[int, ...] = (1, 5, 10)
) -> EvalSummary:
    if not results:
        return EvalSummary(count=0, mrr=0.0, recall_at={k: 0.0 for k in k_values})

    mrr = sum(
        reciprocal_rank(r.ranked_ids, r.expected_paper_id) for r in results
    ) / len(results)
    recall_at = {
        k: sum(1 for r in results if hit_at_k(r.ranked_ids, r.expected_paper_id, k))
        / len(results)
        for k in k_values
    }
    return EvalSummary(count=len(results), mrr=mrr, recall_at=recall_at)
