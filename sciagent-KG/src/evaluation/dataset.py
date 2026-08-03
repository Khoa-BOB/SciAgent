import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from neo4j import Driver

logger = logging.getLogger(__name__)


@dataclass
class EvalQuery:
    query: str
    expected_paper_id: str
    source: str


def load_eval_queries(path: Path) -> list[EvalQuery]:
    queries = []
    with path.open(encoding="utf-8") as eval_file:
        for line in eval_file:
            line = line.strip()
            if not line:
                continue
            queries.append(EvalQuery(**json.loads(line)))
    return queries


def save_eval_queries(queries: Iterable[EvalQuery], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as eval_file:
        for query in queries:
            eval_file.write(json.dumps(asdict(query)) + "\n")


def generate_self_retrieval_queries(
    driver: Driver, database: str | None
) -> list[EvalQuery]:
    """Every paper's own title, paired with its arxiv_id as the expected answer.

    Free and exhaustive (covers the whole corpus, no manual labeling), but
    optimistic -- matching a paper's own title is easier than a query a person
    would actually type. Good as a regression signal ("did this change break
    something"), not an absolute quality benchmark; pair with a curated
    paraphrased set for that.
    """
    records, _, _ = driver.execute_query(
        """
        MATCH (p:Paper)
        WHERE p.title IS NOT NULL AND trim(p.title) <> ""
        RETURN p.arxiv_id AS arxiv_id, p.title AS title
        """,
        database_=database,
        routing_="r",
    )
    return [
        EvalQuery(
            query=record["title"],
            expected_paper_id=record["arxiv_id"],
            source="self_retrieval",
        )
        for record in records
    ]
