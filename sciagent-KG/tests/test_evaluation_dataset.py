from src.evaluation.dataset import (
    EvalQuery,
    generate_self_retrieval_queries,
    load_eval_queries,
    save_eval_queries,
)


class FakeRecord:
    def __init__(self, data: dict):
        self._data = data

    def __getitem__(self, key: str):
        return self._data[key]


class FakeDriver:
    def __init__(self, papers: list[dict]):
        self.papers = papers
        self.queries: list[str] = []

    def execute_query(self, query, **kwargs):
        self.queries.append(query)
        return [FakeRecord(p) for p in self.papers], None, None


def test_save_and_load_round_trip(tmp_path):
    queries = [
        EvalQuery(query="a query", expected_paper_id="1234.5678", source="paraphrased"),
        EvalQuery(query="another query", expected_paper_id="8765.4321", source="self_retrieval"),
    ]
    path = tmp_path / "eval.jsonl"

    save_eval_queries(queries, path)
    loaded = load_eval_queries(path)

    assert loaded == queries


def test_load_eval_queries_skips_blank_lines(tmp_path):
    path = tmp_path / "eval.jsonl"
    path.write_text(
        '{"query": "q1", "expected_paper_id": "1", "source": "s"}\n'
        "\n"
        '{"query": "q2", "expected_paper_id": "2", "source": "s"}\n',
        encoding="utf-8",
    )

    loaded = load_eval_queries(path)

    assert len(loaded) == 2


def test_generate_self_retrieval_queries_pairs_title_with_arxiv_id():
    driver = FakeDriver(
        papers=[
            {"arxiv_id": "0704.0047", "title": "Intelligent location of acoustic sources"},
            {"arxiv_id": "0903.0174", "title": "Accelerating syntactic parsing"},
        ]
    )

    queries = generate_self_retrieval_queries(driver, database=None)

    assert len(queries) == 2
    assert queries[0] == EvalQuery(
        query="Intelligent location of acoustic sources",
        expected_paper_id="0704.0047",
        source="self_retrieval",
    )
    assert all(q.source == "self_retrieval" for q in queries)
