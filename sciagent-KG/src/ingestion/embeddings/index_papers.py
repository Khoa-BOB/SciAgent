import argparse
import logging
from typing import Any, Iterator

from neo4j import Driver
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

from src.config import NEO4J_DATABASE, get_driver

logger = logging.getLogger(__name__)

MODEL_NAME = "google/embeddinggemma-300m"
BATCH_SIZE = 32


def build_paper_text(paper: dict[str, Any]) -> str:
    """Build a text representation of a paper for embedding."""
    title = paper.get("title", "") or ""
    abstract = paper.get("abstract", "") or ""

    return f"Title: {title.strip()}.\nAbstract: {abstract.strip()}."


def load_papers_in_batches(
    driver: Driver,
    database: str | None = None,
    batch_size: int = BATCH_SIZE,
    limit: int | None = None,
    property_name: str = "embedding",
    only_missing: bool = True,
) -> Iterator[list[dict[str, Any]]]:
    """Yield papers from Neo4j in batches, stopping early once `limit` papers have been yielded.

    When `only_missing` is True (the default), papers that already have a value
    in `property_name` are skipped, so re-running the embedder only does work
    for newly-loaded papers instead of recomputing everything.
    """

    last_id: str | None = None
    loaded = 0
    missing_clause = (
        "AND p[$property] IS NULL" if only_missing else ""
    )

    while True:
        remaining = batch_size if limit is None else min(batch_size, limit - loaded)
        if remaining <= 0:
            break

        records, _, _ = driver.execute_query(
            f"""
            MATCH (p:Paper)
            WHERE p.title IS NOT NULL
              AND p.abstract IS NOT NULL
              AND trim(p.abstract) <> ""
              AND ($last_id IS NULL OR p.arxiv_id > $last_id)
              {missing_clause}
            RETURN p.arxiv_id AS arxiv_id,
                   p.title AS title,
                   p.abstract AS abstract
            ORDER BY p.arxiv_id
            LIMIT $batch_size
            """,
            last_id=last_id,
            batch_size=remaining,
            property=property_name,
            database_=database,
            routing_="r",
        )

        batch = [record.data() for record in records]

        if not batch:
            break

        yield batch
        loaded += len(batch)
        last_id = batch[-1]["arxiv_id"]


def save_embeddings(
    driver: Driver,
    database: str | None,
    rows: list[dict[str, Any]],
    model_name: str,
    property_name: str,
) -> None:
    """Save embeddings to Neo4j."""
    driver.execute_query(
        """
        UNWIND $rows AS row
        MATCH (p:Paper {arxiv_id: row.arxiv_id})
        SET p[$property] = row.embedding,
            p[$property + "_model"] = $model_name
        """,
        rows=rows,
        model_name=model_name,
        property=property_name,
        database_=database,
    )


def run_embedding(
    driver: Driver,
    model: SentenceTransformer,
    *,
    database: str | None = NEO4J_DATABASE,
    limit: int | None = None,
    batch_size: int = BATCH_SIZE,
    property_name: str = "embedding",
    model_name: str = MODEL_NAME,
    prompt_name: str | None = "document",
    only_missing: bool = True,
    dry_run: bool = False,
) -> int:
    """Fetch, embed, and save papers batch-by-batch, returning the total embedded."""
    logger.info(
        "Embedding with model=%r into property=%r (only_missing=%s)",
        model_name,
        property_name,
        only_missing,
    )

    total_embedded = 0
    batches = load_papers_in_batches(
        driver,
        database,
        batch_size=batch_size,
        limit=limit,
        property_name=property_name,
        only_missing=only_missing,
    )

    for batch in tqdm(batches, desc="Embedding batches", unit="batch"):
        texts = [build_paper_text(paper) for paper in batch]

        embeddings = model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
            prompt_name=prompt_name,
        )

        rows = [
            {
                "arxiv_id": paper["arxiv_id"],
                "embedding": embedding.tolist(),
            }
            for paper, embedding in zip(batch, embeddings)
        ]

        if dry_run:
            sample = rows[0]
            logger.info(
                "[dry-run] Would embed %d papers into property=%r, e.g. %s: %s...",
                len(rows),
                property_name,
                sample["arxiv_id"],
                sample["embedding"][:5],
            )
        else:
            save_embeddings(
                driver,
                database,
                rows,
                model_name=model_name,
                property_name=property_name,
            )

        total_embedded += len(rows)
        logger.info("Embedded %d paper(s) so far", total_embedded)

    return total_embedded


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Embed papers and store vectors in Neo4j.")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only embed the first N eligible papers (useful for testing before a full run).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=BATCH_SIZE,
        help="Number of papers fetched from Neo4j and embedded per batch (default: %(default)s)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute embeddings but don't write them to Neo4j.",
    )
    parser.add_argument(
        "--model",
        default=MODEL_NAME,
        help="SentenceTransformer model to embed with (default: %(default)s)",
    )
    parser.add_argument(
        "--property",
        default="embedding",
        help="Paper property to write the embedding vector to (default: %(default)s). "
        "The model name is recorded alongside it as '<property>_model'.",
    )
    parser.add_argument(
        "--prompt-name",
        default="document",
        help="Prompt name to pass to model.encode() for models with asymmetric "
        "query/document prompts (default: %(default)s, matching the current "
        "production model google/embeddinggemma-300m). Pass '' to disable "
        "for symmetric models like MiniLM.",
    )
    parser.add_argument(
        "--reembed-all",
        action="store_true",
        help="Recompute embeddings for every eligible paper, including ones that "
        "already have a value in --property (default: only embed papers missing it).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (default: %(default)s)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=args.log_level, format="%(asctime)s %(levelname)s %(message)s"
    )

    model = SentenceTransformer(args.model)
    driver = get_driver()

    try:
        driver.verify_connectivity()
        total_embedded = run_embedding(
            driver,
            model,
            database=NEO4J_DATABASE,
            limit=args.limit,
            batch_size=args.batch_size,
            property_name=args.property,
            model_name=args.model,
            prompt_name=args.prompt_name or None,
            only_missing=not args.reembed_all,
            dry_run=args.dry_run,
        )
        logger.info("Done. Embedded %d paper(s) total.", total_embedded)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
