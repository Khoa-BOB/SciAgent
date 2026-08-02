import argparse
import os
from typing import Any, Iterator
from neo4j import Driver

from dotenv import load_dotenv
from neo4j import GraphDatabase
from sentence_transformers import SentenceTransformer

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
BATCH_SIZE = 32

def build_paper_text(paper: dict[str, Any])-> str:
    """Build a text representation of a paper for embedding."""
    title = paper.get("title", "") or ""
    abstract = paper.get("abstract", "") or ""
    
    return f"Title: {title.strip()}.\nAbstract: {abstract.strip()}."

def load_papers_in_batches(
    driver: Driver,
    database: str | None = None,
    batch_size: int = BATCH_SIZE,
    limit: int | None = None,
) -> Iterator[list[dict[str, Any]]]:
    """Yield papers from Neo4j in batches, stopping early once `limit` papers have been yielded."""

    last_id: str | None = None
    loaded = 0

    while True:
        remaining = batch_size if limit is None else min(batch_size, limit - loaded)
        if remaining <= 0:
            break

        records, _, _ = driver.execute_query(
            """
            MATCH (p:Paper)
            WHERE p.title IS NOT NULL
              AND p.abstract IS NOT NULL
              AND trim(p.abstract) <> ""
              AND ($last_id IS NULL OR p.arxiv_id > $last_id)
            RETURN p.arxiv_id AS arxiv_id,
                   p.title AS title,
                   p.abstract AS abstract
            ORDER BY p.arxiv_id
            LIMIT $batch_size
            """,
            last_id=last_id,
            batch_size=remaining,
            database_=database,
            routing_="r",
        )

        batch = [record.data() for record in records]

        if not batch:
            break

        yield batch
        loaded += len(batch)
        last_id = batch[-1]["arxiv_id"]

def save_embeddings(driver: Driver, database: str | None, rows: list[dict[str, Any]]) -> None:
    """Save embeddings to Neo4j."""
    driver.execute_query(
        """
        UNWIND $rows AS row
        MATCH (p:Paper {arxiv_id: row.arxiv_id})
        SET p.embedding = row.embedding,
            p.embedding_model = $model_name
        """,
        rows=rows,
        model_name=MODEL_NAME,
        database_=database,
    )

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Embed papers and store vectors in Neo4j.")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only embed the first N eligible papers (useful for testing before a full run).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute embeddings but don't write them to Neo4j.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_dotenv()

    uri = os.environ["NEO4J_URI"]
    username = os.environ["NEO4J_USERNAME"]
    password = os.environ["NEO4J_PASSWORD"]
    database = os.getenv("NEO4J_DATABASE", "neo4j")

    model = SentenceTransformer(MODEL_NAME)

    with GraphDatabase.driver(
        uri,
        auth=(username, password),
    ) as driver:
        driver.verify_connectivity()

        papers = list(load_papers_in_batches(driver, database, limit=args.limit))  # Convert the iterator to a list of batches
        papers = [paper for batch in papers for paper in batch]  # Flatten the list of batches
        print(f"Loaded {len(papers)} papers")

        for start in range(0, len(papers), BATCH_SIZE):
            batch = papers[start : start + BATCH_SIZE]
            texts = [build_paper_text(paper) for paper in batch]

            embeddings = model.encode(
                texts,
                batch_size=BATCH_SIZE,
                normalize_embeddings=True,
                show_progress_bar=False,
            )

            rows = [
                {
                    "arxiv_id": paper["arxiv_id"],
                    "embedding": embedding.tolist(),
                }
                for paper, embedding in zip(batch, embeddings)
            ]

            if args.dry_run:
                sample = rows[0]
                print(
                    f"[dry-run] Would embed {len(rows)} papers, "
                    f"e.g. {sample['arxiv_id']}: {sample['embedding'][:5]}..."
                )
            else:
                save_embeddings(driver, database, rows)

            completed = min(start + BATCH_SIZE, len(papers))
            print(f"Embedded {completed}/{len(papers)} papers")


if __name__ == "__main__":
    main()