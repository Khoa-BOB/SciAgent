import numpy as np

from src.extraction.resolve import (
    _acronym_fallback_match,
    _initials,
    _is_acronym_token,
    cluster_names,
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
    mapping = cluster_names(["convolutional neural network", "CNN"], model, threshold=0.85)
    assert mapping["CNN"] == "convolutional neural network"
    assert mapping["convolutional neural network"] == "convolutional neural network"


def test_cluster_names_merges_expansion_into_existing_acronym() -> None:
    # Reverse order: the acronym is more frequent and becomes canonical
    # first; the expansion should still join it via the acronym fallback.
    model = FakeModel()
    mapping = cluster_names(["MCTS", "Monte Carlo Tree Search"], model, threshold=0.85)
    assert mapping["Monte Carlo Tree Search"] == "MCTS"
    assert mapping["MCTS"] == "MCTS"


def test_cluster_names_cosine_merge_still_works() -> None:
    # Regression check: the acronym fallback is additive, not a replacement
    # for the existing embedding-similarity path.
    model = FakeModel(vectors={"CNNs": [1.0, 0.0], "CNN": [0.99, 0.01]})
    mapping = cluster_names(["CNNs", "CNN"], model, threshold=0.85)
    assert mapping["CNN"] == "CNNs"


def test_cluster_names_merges_acronym_pair_but_not_an_unrelated_name() -> None:
    # "RL" and "reinforcement learning" are a real acronym/expansion pair
    # (should merge); "graph neural network" shares no relation to either
    # and must stay in its own cluster.
    model = FakeModel()
    mapping = cluster_names(["graph neural network", "RL", "reinforcement learning"], model, threshold=0.85)
    assert mapping["graph neural network"] == "graph neural network"
    assert mapping["reinforcement learning"] == "RL"
    assert mapping["RL"] == "RL"


def test_cluster_names_empty_input() -> None:
    assert cluster_names([], FakeModel(), threshold=0.85) == {}
