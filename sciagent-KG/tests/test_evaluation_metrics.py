from src.evaluation.metrics import QueryResult, hit_at_k, reciprocal_rank, summarize


def test_reciprocal_rank_first_position():
    assert reciprocal_rank(["a", "b", "c"], "a") == 1.0


def test_reciprocal_rank_third_position():
    assert reciprocal_rank(["a", "b", "c"], "c") == 1.0 / 3


def test_reciprocal_rank_not_found():
    assert reciprocal_rank(["a", "b", "c"], "z") == 0.0


def test_hit_at_k_within_range():
    assert hit_at_k(["a", "b", "c"], "b", k=2) is True


def test_hit_at_k_outside_range():
    assert hit_at_k(["a", "b", "c"], "c", k=2) is False


def test_summarize_empty_results():
    summary = summarize([], k_values=(1, 5))
    assert summary.count == 0
    assert summary.mrr == 0.0
    assert summary.recall_at == {1: 0.0, 5: 0.0}


def test_summarize_mixed_results():
    results = [
        QueryResult(query="q1", expected_paper_id="a", source="s", ranked_ids=["a", "b"]),
        QueryResult(query="q2", expected_paper_id="x", source="s", ranked_ids=["a", "b"]),
    ]
    summary = summarize(results, k_values=(1, 2))

    assert summary.count == 2
    assert summary.mrr == 0.5  # (1.0 + 0.0) / 2
    assert summary.recall_at[1] == 0.5  # only q1 hits within top-1
    assert summary.recall_at[2] == 0.5  # q2's expected id never appears
