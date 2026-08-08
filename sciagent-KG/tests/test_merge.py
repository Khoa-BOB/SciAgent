"""Unit tests for src.extraction.merge -- the embedding-caching helpers in
particular (fetch_existing_clusters, backfill_entity_embeddings, and
merge_resolved's new_embeddings wiring). Mocks the Neo4j driver directly, no
live database needed.
"""

from unittest.mock import MagicMock

import numpy as np

from src.extraction.merge import (
    backfill_entity_embeddings,
    fetch_existing_clusters,
    merge_resolved,
)


class _FakeRecord(dict):
    def data(self):
        return dict(self)


def test_merge_resolved_attaches_embedding_only_for_new_entities():
    driver = MagicMock()
    driver.execute_query.return_value = ([], None, None)

    rows = [
        {
            "paper_id": "2401.00001",
            "entity_type": "method",
            "name": "graph neural network",
            "normalized_name": "graph neural network",
            "raw_name": "GNN",
        },
        {
            "paper_id": "2401.00002",
            "entity_type": "method",
            "name": "an already-existing entity",
            "normalized_name": "an already-existing entity",
            "raw_name": "an already-existing entity",
        },
    ]
    new_embeddings = {"method": {"graph neural network": np.array([0.1, 0.2, 0.3])}}

    merge_resolved(driver, "neo4j", rows, new_embeddings=new_embeddings)

    entity_calls = [call for call in driver.execute_query.call_args_list if "rows" in call.kwargs]
    upsert_call = next(call for call in entity_calls if any("normalized_name" in r and "embedding" in r for r in call.kwargs["rows"]))
    rows_by_name = {row["normalized_name"]: row for row in upsert_call.kwargs["rows"]}

    assert rows_by_name["graph neural network"]["embedding"] == [0.1, 0.2, 0.3]
    assert rows_by_name["an already-existing entity"]["embedding"] is None


def test_merge_resolved_without_new_embeddings_sends_none():
    driver = MagicMock()
    driver.execute_query.return_value = ([], None, None)

    rows = [
        {
            "paper_id": "2401.00001",
            "entity_type": "dataset",
            "name": "ogbn-arxiv",
            "normalized_name": "ogbn-arxiv",
            "raw_name": "ogbn-arxiv",
        }
    ]

    merge_resolved(driver, "neo4j", rows)

    entity_calls = [call for call in driver.execute_query.call_args_list if "rows" in call.kwargs]
    upsert_call = entity_calls[0]
    assert upsert_call.kwargs["rows"][0]["embedding"] is None


def test_fetch_existing_clusters_builds_per_type_structure():
    driver = MagicMock()

    def fake_execute_query(query, **kwargs):
        if "Method" in query:
            return ([_FakeRecord(name="graph neural network", embedding=[0.1, 0.2])], None, None)
        return ([], None, None)

    driver.execute_query.side_effect = fake_execute_query

    existing = fetch_existing_clusters(driver, "neo4j")

    # Compare structurally since np arrays don't support == on tuples cleanly.
    assert len(existing["method"]) == 1
    name, embedding = existing["method"][0]
    assert name == "graph neural network"
    assert np.array_equal(embedding, np.array([0.1, 0.2], dtype=np.float32))
    assert existing["dataset"] == []
    assert existing["topic"] == []


def test_backfill_entity_embeddings_only_touches_missing_and_is_idempotent():
    driver = MagicMock()

    def fake_execute_query(query, **kwargs):
        if "WHERE e.embedding IS NULL" in query and "Method" in query:
            return (
                [_FakeRecord(normalized_name="cnn", name="CNN"), _FakeRecord(normalized_name="rl", name="RL")],
                None,
                None,
            )
        if "WHERE e.embedding IS NULL" in query:
            return ([], None, None)
        return ([], None, None)

    driver.execute_query.side_effect = fake_execute_query

    model = MagicMock()
    model.encode.return_value = np.array([[0.1, 0.2], [0.3, 0.4]])

    counts = backfill_entity_embeddings(driver, "neo4j", model)

    assert counts == {"method": 2, "dataset": 0, "topic": 0}
    model.encode.assert_called_once_with(["CNN", "RL"], normalize_embeddings=True, show_progress_bar=False)

    set_calls = [
        call
        for call in driver.execute_query.call_args_list
        if "rows" in call.kwargs and "SET e.embedding" in call.args[0]
    ]
    assert len(set_calls) == 1
    written = {row["normalized_name"]: row["embedding"] for row in set_calls[0].kwargs["rows"]}
    assert written["cnn"] == [0.1, 0.2]
    assert written["rl"] == [0.3, 0.4]
