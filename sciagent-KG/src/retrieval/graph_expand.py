from dataclasses import dataclass, field

from queries.expansion import RELATED_BY_AUTHOR, RELATED_BY_CATEGORY, SEED_CONTEXT
from src.config import NEO4J_DATABASE, get_driver

DEFAULT_RELATED_LIMIT = 5
DEFAULT_POOL_SIZE = 20

AUTHOR_WEIGHT = 0.1
CATEGORY_WEIGHT = 0.05


@dataclass
class PaperContext:
    paper_id: str
    authors: list[str]
    categories: list[str]
    journal: str | None


@dataclass
class RelatedPaper:
    paper_id: str
    title: str
    shared_authors: list[str] = field(default_factory=list)
    shared_categories: list[str] = field(default_factory=list)
    similarity_to_query: float = 0.0


@dataclass
class ExpandedResult:
    seed_context: dict[str, PaperContext]
    related_papers: list[RelatedPaper]


class GraphExpander:
    def __init__(self) -> None:
        self.database = NEO4J_DATABASE
        self.driver = get_driver()

    def close(self) -> None:
        self.driver.close()

    def expand(
        self,
        paper_ids: list[str],
        query_embedding: list[float] | None = None,
        related_limit: int = DEFAULT_RELATED_LIMIT,
        pool_size: int = DEFAULT_POOL_SIZE,
    ) -> ExpandedResult:
        if not paper_ids:
            return ExpandedResult(seed_context={}, related_papers=[])

        return ExpandedResult(
            seed_context=self._fetch_seed_context(paper_ids),
            related_papers=self._fetch_related_papers(
                paper_ids,
                query_embedding=query_embedding,
                related_limit=related_limit,
                pool_size=pool_size,
            ),
        )

    def _fetch_seed_context(self, paper_ids: list[str]) -> dict[str, PaperContext]:
        """Fetches the seed context for the given paper IDs from the Neo4j database."""
        records, _, _ = self.driver.execute_query(
            SEED_CONTEXT,
            paper_ids=paper_ids,
            database_=self.database,
            routing_="r",
        )
        return {
            record["paper_id"]: PaperContext(
                paper_id=record["paper_id"],
                authors=record["authors"],
                categories=record["categories"],
                journal=record["journal"],
            )
            for record in records
        }

    def _fetch_related_papers(
        self,
        paper_ids: list[str],
        query_embedding: list[float] | None,
        related_limit: int,
        pool_size: int,
    ) -> list[RelatedPaper]:
        """Fetches related papers based on shared authors and categories from the Neo4j database."""
        by_author, _, _ = self.driver.execute_query(
            RELATED_BY_AUTHOR,
            paper_ids=paper_ids,
            pool_size=pool_size,
            database_=self.database,
            routing_="r",
        )
        by_category, _, _ = self.driver.execute_query(
            RELATED_BY_CATEGORY,
            paper_ids=paper_ids,
            pool_size=pool_size,
            database_=self.database,
            routing_="r",
        )

        merged: dict[str, RelatedPaper] = {}
        embeddings: dict[str, list[float]] = {}

        for record in by_author:
            merged[record["paper_id"]] = RelatedPaper(
                paper_id=record["paper_id"],
                title=record["title"],
                shared_authors=record["shared_authors"],
            )
            embeddings[record["paper_id"]] = record["embedding"]

        for record in by_category:
            related = merged.setdefault(
                record["paper_id"],
                RelatedPaper(paper_id=record["paper_id"], title=record["title"]),
            )
            related.shared_categories = record["shared_categories"]
            embeddings.setdefault(record["paper_id"], record["embedding"])

        if query_embedding is None:
            ranked = sorted(
                merged.values(),
                key=lambda r: (len(r.shared_authors), len(r.shared_categories)),
                reverse=True,
            )
            return ranked[:related_limit]

        for paper_id, related in merged.items():
            embedding = embeddings.get(paper_id)
            if embedding is not None:
                related.similarity_to_query = _cosine_similarity(
                    embedding, query_embedding
                )

        ranked = sorted(
            merged.values(),
            key=lambda r: (
                r.similarity_to_query
                + AUTHOR_WEIGHT * len(r.shared_authors)
                + CATEGORY_WEIGHT * len(r.shared_categories)
            ),
            reverse=True,
        )
        return ranked[:related_limit]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    # Both vectors come from the same normalized SentenceTransformer model,
    # so a plain dot product already equals cosine similarity.
    return sum(x * y for x, y in zip(a, b))
