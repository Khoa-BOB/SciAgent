import json

import numpy as np

from src.extraction.resolve import (
    _acronym_fallback_match,
    _initials,
    _is_acronym_token,
    cluster_names,
    resolve,
)


class FakeModel:
    """Returns a controlled embedding per name so cosine similarity outcomes
    are deterministic in tests -- explicitly-vectored names get exactly
    that vector (normalized), everything else gets a distinct near-orthogonal
    default vector so unrelated names never accidentally cluster."""

    def __init__(self, vectors: dict[str, list[float]] | None = None, dim: int = 8):
        self.vectors = vectors or {}
        self.dim = dim

    def encode(self, names, normalize_embeddings=True, show_progress_bar=False):
        rows = []
        for index, name in enumerate(names):
            vector = self.vectors.get(name)
            if vector is None:
                vector = [0.0] * self.dim
                vector[index % self.dim] = 1.0
            array = np.array(vector, dtype=float)
            if normalize_embeddings:
                norm = np.linalg.norm(array)
                if norm > 0:
                    array = array / norm
            rows.append(array)
        return np.array(rows)


def test_initials_from_multiword_name() -> None:
    assert _initials("convolutional neural network") == "CNN"
    assert _initials("Monte Carlo Tree Search") == "MCTS"
    assert _initials("reinforcement learning") == "RL"


def test_is_acronym_token() -> None:
    assert _is_acronym_token("CNN") is True
    assert _is_acronym_token("RL") is True
    assert _is_acronym_token("convolutional neural network") is False
    assert _is_acronym_token("cnn") is False  # lowercase -- not how the LLM would write an acronym
    assert _is_acronym_token("A") is False  # single letter, below the 2-char floor
    assert _is_acronym_token("TOOLONGACRONYM") is False  # above the 6-char ceiling


def test_acronym_fallback_match_both_directions() -> None:
    acronym_to_cluster = {"CNN": 0}
    initials_to_cluster = {"RL": 1}

    assert _acronym_fallback_match("convolutional neural network", acronym_to_cluster, initials_to_cluster) == 0
    assert _acronym_fallback_match("RL", acronym_to_cluster, initials_to_cluster) == 1
    assert _acronym_fallback_match("unrelated phrase here", acronym_to_cluster, initials_to_cluster) is None


def test_cluster_names_merges_acronym_into_existing_expansion() -> None:
    # "CNN" processed after its expansion (frequency order: expansion first).
    # Default fallback vectors keep their cosine similarity near zero, so
    # this only merges via the acronym fallback, not the embedding check.
    model = FakeModel()
    mapping, new_embeddings = cluster_names(["convolutional neural network", "CNN"], model, threshold=0.85)
    assert mapping["CNN"] == "convolutional neural network"
    assert mapping["convolutional neural network"] == "convolutional neural network"
    # Exactly one canonical entity was created ("CNN" joined the existing one).
    assert set(new_embeddings) == {"convolutional neural network"}


def test_cluster_names_merges_expansion_into_existing_acronym() -> None:
    # Reverse order: the acronym is more frequent and becomes canonical
    # first; the expansion should still join it via the acronym fallback.
    model = FakeModel()
    mapping, new_embeddings = cluster_names(["MCTS", "Monte Carlo Tree Search"], model, threshold=0.85)
    assert mapping["Monte Carlo Tree Search"] == "MCTS"
    assert mapping["MCTS"] == "MCTS"
    assert set(new_embeddings) == {"MCTS"}


def test_cluster_names_cosine_merge_still_works() -> None:
    # Regression check: the acronym fallback is additive, not a replacement
    # for the existing embedding-similarity path.
    model = FakeModel(vectors={"CNNs": [1.0, 0.0], "CNN": [0.99, 0.01]})
    mapping, new_embeddings = cluster_names(["CNNs", "CNN"], model, threshold=0.85)
    assert mapping["CNN"] == "CNNs"
    assert set(new_embeddings) == {"CNNs"}


def test_cluster_names_merges_acronym_pair_but_not_an_unrelated_name() -> None:
    # "RL" and "reinforcement learning" are a real acronym/expansion pair
    # (should merge); "graph neural network" shares no relation to either
    # and must stay in its own cluster.
    model = FakeModel()
    mapping, new_embeddings = cluster_names(
        ["graph neural network", "RL", "reinforcement learning"], model, threshold=0.85
    )
    assert mapping["graph neural network"] == "graph neural network"
    assert mapping["reinforcement learning"] == "RL"
    assert mapping["RL"] == "RL"
    assert set(new_embeddings) == {"graph neural network", "RL"}


def test_cluster_names_empty_input() -> None:
    assert cluster_names([], FakeModel(), threshold=0.85) == ({}, {})


# --- Seeded (incremental) clustering ----------------------------------------


def test_cluster_names_new_name_joins_existing_seeded_cluster_via_cosine() -> None:
    seed_embedding = np.array([1.0, 0.0])
    seed_embedding = seed_embedding / np.linalg.norm(seed_embedding)
    existing_clusters = [("convolutional neural network", seed_embedding)]

    model = FakeModel(vectors={"Convolutional Neural Networks": [0.99, 0.01]})
    mapping, new_embeddings = cluster_names(
        ["Convolutional Neural Networks"], model, threshold=0.85, existing_clusters=existing_clusters
    )

    assert mapping["Convolutional Neural Networks"] == "convolutional neural network"
    # Joined an existing cluster -- nothing new was created, so nothing
    # needs to be persisted back to Neo4j for this name.
    assert new_embeddings == {}


def test_cluster_names_new_name_joins_existing_seeded_cluster_via_acronym() -> None:
    seed_embedding = np.zeros(8)
    seed_embedding[0] = 1.0
    existing_clusters = [("convolutional neural network", seed_embedding)]

    # Default FakeModel vector for "CNN" is near-orthogonal to the seed, so
    # this only merges via the acronym fallback, not cosine similarity.
    model = FakeModel()
    mapping, new_embeddings = cluster_names(["CNN"], model, threshold=0.85, existing_clusters=existing_clusters)

    assert mapping["CNN"] == "convolutional neural network"
    assert new_embeddings == {}


def test_cluster_names_unrelated_new_name_still_creates_its_own_cluster() -> None:
    # Seed vector deliberately doesn't collide with FakeModel's index-based
    # default for a single-name `names` list (which would use index 0).
    seed_embedding = np.zeros(8)
    seed_embedding[3] = 1.0
    existing_clusters = [("convolutional neural network", seed_embedding)]

    model = FakeModel()
    mapping, new_embeddings = cluster_names(
        ["reinforcement learning"], model, threshold=0.85, existing_clusters=existing_clusters
    )

    assert mapping["reinforcement learning"] == "reinforcement learning"
    assert set(new_embeddings) == {"reinforcement learning"}


def test_cluster_names_seeded_names_never_appear_in_mapping_or_new_embeddings() -> None:
    seed_embedding = np.zeros(8)
    seed_embedding[3] = 1.0
    existing_clusters = [("convolutional neural network", seed_embedding)]

    model = FakeModel()
    mapping, new_embeddings = cluster_names(
        ["reinforcement learning"], model, threshold=0.85, existing_clusters=existing_clusters
    )

    # Only names passed in `names` show up in the outputs -- existing_clusters
    # entries are seed state, not something this call re-emits or re-persists.
    assert "convolutional neural network" not in mapping
    assert "convolutional neural network" not in new_embeddings


# --- resolve() end to end ----------------------------------------------------


def _write_extracted_shard(shards_dir, filename, records):
    shards_dir.mkdir(parents=True, exist_ok=True)
    path = shards_dir / filename
    with path.open("w", encoding="utf-8") as extracted_file:
        for record in records:
            extracted_file.write(json.dumps(record) + "\n")
    return path


def test_resolve_reuses_passed_in_model(tmp_path) -> None:
    shards_dir = tmp_path / "shards"
    _write_extracted_shard(
        shards_dir,
        "shard_0000.extracted.jsonl",
        [
            {
                "paper_id": "2401.00001",
                "entities": [{"name": "graph neural network", "type": "method"}],
                "extraction_model": "test-model",
                "extracted_at": "2026-01-01T00:00:00+00:00",
            }
        ],
    )

    rows, new_embeddings = resolve(shards_dir, model=FakeModel())

    assert len(rows) == 1
    assert rows[0]["name"] == "graph neural network"
    assert rows[0]["normalized_name"] == "graph neural network"
    assert set(new_embeddings["method"]) == {"graph neural network"}


def test_resolve_threads_existing_clusters_per_type(tmp_path) -> None:
    shards_dir = tmp_path / "shards"
    _write_extracted_shard(
        shards_dir,
        "shard_0000.extracted.jsonl",
        [
            {
                "paper_id": "2401.00001",
                "entities": [{"name": "CNN", "type": "method"}],
                "extraction_model": "test-model",
                "extracted_at": "2026-01-01T00:00:00+00:00",
            }
        ],
    )

    seed_embedding = np.zeros(8)
    seed_embedding[3] = 1.0
    existing_clusters = {"method": [("convolutional neural network", seed_embedding)]}

    rows, new_embeddings = resolve(shards_dir, model=FakeModel(), existing_clusters=existing_clusters)

    assert rows[0]["name"] == "convolutional neural network"
    assert rows[0]["normalized_name"] == "convolutional neural network"
    # Joined the seeded cluster -- nothing new to persist for this type.
    assert new_embeddings["method"] == {}


def test_resolve_new_embeddings_are_keyed_by_normalized_name(tmp_path) -> None:
    shards_dir = tmp_path / "shards"
    _write_extracted_shard(
        shards_dir,
        "shard_0000.extracted.jsonl",
        [
            {
                "paper_id": "2401.00001",
                "entities": [{"name": "Graph Neural Network", "type": "method"}],
                "extraction_model": "test-model",
                "extracted_at": "2026-01-01T00:00:00+00:00",
            }
        ],
    )

    rows, new_embeddings = resolve(shards_dir, model=FakeModel())

    assert rows[0]["normalized_name"] == "graph neural network"
    # Keyed by normalized_name (lowercase), not the display name.
    assert set(new_embeddings["method"]) == {"graph neural network"}


def test_resolve_empty_shards_dir_returns_empty(tmp_path) -> None:
    shards_dir = tmp_path / "shards"
    shards_dir.mkdir()
    rows, new_embeddings = resolve(shards_dir, model=FakeModel())
    assert rows == []
    assert new_embeddings == {}
