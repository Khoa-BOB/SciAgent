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


def get_corpus_size(driver: Driver, database: str | None) -> int:
    records, _, _ = driver.execute_query(
        "MATCH (p:Paper) RETURN count(p) AS c",
        database_=database,
        routing_="r",
    )
    return records[0]["c"]


@dataclass
class ExpansionCase:
    seed_id: str
    seed_embedding: list[float]
    expected_id: str
    source: str


_EXPANSION_QUERIES: dict[str, str] = {
    # For each author/category with >=2 embedded papers, take the first two
    # (by arxiv_id, for determinism) as a (seed, expected) pair. `expected`
    # is guaranteed connected to `seed` by that relation, so this checks
    # whether GraphExpander actually surfaces known-connected papers -- not
    # full topical relevance, which we have no ground truth for.
    "shared_author": """
        MATCH (a:Author)-[:AUTHORED]->(p:Paper)
        WHERE p.embedding IS NOT NULL
        WITH a, p ORDER BY p.arxiv_id
        WITH a, collect({id: p.arxiv_id, embedding: p.embedding}) AS papers
        WHERE size(papers) >= 2
        RETURN papers[0].id AS seed_id, papers[0].embedding AS seed_embedding,
               papers[1].id AS expected_id
        LIMIT $limit
    """,
    "shared_category": """
        MATCH (c:Category)<-[:IN_CATEGORY]-(p:Paper)
        WHERE p.embedding IS NOT NULL
        WITH c, p ORDER BY p.arxiv_id
        WITH c, collect({id: p.arxiv_id, embedding: p.embedding}) AS papers
        WHERE size(papers) >= 2
        RETURN papers[0].id AS seed_id, papers[0].embedding AS seed_embedding,
               papers[1].id AS expected_id
        LIMIT $limit
    """,
}


def generate_expansion_cases(
    driver: Driver, database: str | None, source: str, limit: int = 500
) -> list[ExpansionCase]:
    records, _, _ = driver.execute_query(
        _EXPANSION_QUERIES[source],
        limit=limit,
        database_=database,
        routing_="r",
    )
    return [
        ExpansionCase(
            seed_id=record["seed_id"],
            seed_embedding=record["seed_embedding"],
            expected_id=record["expected_id"],
            source=source,
        )
        for record in records
    ]


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
