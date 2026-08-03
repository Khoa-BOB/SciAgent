import json

from src.ingestion.sampling import reservoir_sample


def _write_corpus(path, n: int) -> None:
    with path.open("w", encoding="utf-8") as f:
        for i in range(n):
            f.write(json.dumps({"id": f"corpus.{i:05d}"}) + "\n")


def test_reservoir_sample_is_deterministic_for_same_seed(tmp_path):
    corpus_path = tmp_path / "corpus.jsonl"
    _write_corpus(corpus_path, 200)

    first = reservoir_sample(corpus_path, n=20, seed=42)
    second = reservoir_sample(corpus_path, n=20, seed=42)

    assert first == second
    assert len(first) == 20


def test_reservoir_sample_differs_across_seeds(tmp_path):
    corpus_path = tmp_path / "corpus.jsonl"
    _write_corpus(corpus_path, 200)

    a = reservoir_sample(corpus_path, n=20, seed=1)
    b = reservoir_sample(corpus_path, n=20, seed=2)

    assert a != b


def test_reservoir_sample_skips_invalid_json(tmp_path):
    corpus_path = tmp_path / "corpus.jsonl"
    with corpus_path.open("w", encoding="utf-8") as f:
        f.write(json.dumps({"id": "ok.0001"}) + "\n")
        f.write("not valid json\n")
        f.write(json.dumps({"id": "ok.0002"}) + "\n")

    sample = reservoir_sample(corpus_path, n=10, seed=42)

    assert len(sample) == 2
    parsed_ids = {json.loads(line)["id"] for line in sample}
    assert parsed_ids == {"ok.0001", "ok.0002"}


def test_reservoir_sample_caps_at_corpus_size(tmp_path):
    corpus_path = tmp_path / "corpus.jsonl"
    _write_corpus(corpus_path, 5)

    sample = reservoir_sample(corpus_path, n=100, seed=42)

    assert len(sample) == 5
