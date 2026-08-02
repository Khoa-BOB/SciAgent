from queries.metadata import UPSERT_PAPER


def test_upsert_paper_concludes_after_final_subquery():
    assert UPSERT_PAPER.strip().endswith("RETURN p.arxiv_id AS arxiv_id")
