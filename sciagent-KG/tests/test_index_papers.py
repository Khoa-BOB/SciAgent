from src.ingestion.embeddings.index_papers import run_embedding


class FakeVector(list):
    def tolist(self):
        return list(self)


class FakeModel:
    def __init__(self):
        self.encode_calls = 0

    def encode(self, texts, **kwargs):
        self.encode_calls += 1
        return [FakeVector([0.1, 0.2, 0.3]) for _ in texts]


class FakeRecord:
    def __init__(self, data: dict):
        self._data = data

    def data(self) -> dict:
        return self._data


class FakeEmbeddingDriver:
    """Fake neo4j Driver for index_papers tests: serves paginated `fetch`
    results and records the call order (fetch vs save) and each raw query
    text, so tests can assert the fetch/embed/save loop is interleaved
    per-batch rather than draining every page before embedding anything."""

    def __init__(self, pages: list[list[dict]]):
        self.pages = list(pages)
        self.call_order: list[str] = []
        self.queries: list[str] = []

    def execute_query(self, query, **kwargs):
        self.queries.append(query)
        if "MATCH (p:Paper)" in query:
            self.call_order.append("fetch")
            page = self.pages.pop(0) if self.pages else []
            return [FakeRecord(row) for row in page], None, None
        if "UNWIND $rows" in query:
            self.call_order.append("save")
            return [], None, None
        raise AssertionError(f"Unexpected query: {query}")


def _page(n: int, start: int) -> list[dict]:
    return [
        {"arxiv_id": f"1000.{i:04d}", "title": "t", "abstract": "a"}
        for i in range(start, start + n)
    ]


def test_embedding_interleaves_fetch_and_save_per_batch():
    driver = FakeEmbeddingDriver(pages=[_page(2, 1), _page(2, 3)])
    model = FakeModel()

    total = run_embedding(driver, model, database=None, batch_size=2)

    assert total == 4
    # A save must follow each fetch immediately -- if the generator were
    # drained into a list first (the original bug), every fetch would
    # happen before any save.
    assert driver.call_order == ["fetch", "save", "fetch", "save", "fetch"]


def test_only_missing_filter_present_by_default():
    driver = FakeEmbeddingDriver(pages=[])
    model = FakeModel()

    run_embedding(driver, model, database=None, batch_size=2, only_missing=True)

    assert any("p[$property] IS NULL" in q for q in driver.queries)


def test_only_missing_filter_absent_when_reembed_all():
    driver = FakeEmbeddingDriver(pages=[])
    model = FakeModel()

    run_embedding(driver, model, database=None, batch_size=2, only_missing=False)

    assert all("p[$property] IS NULL" not in q for q in driver.queries)
