from dataclasses import dataclass

from queries.search import (
    FULLTEXT_SEARCH,
    PAPER_BY_ID,
    PAPERS_BY_AUTHOR,
    PAPERS_BY_CATEGORY,
    PAPERS_BY_YEAR,
)
from src.config import NEO4J_DATABASE, get_driver
from src.text_utils import normalize_name


@dataclass
class PaperDetails:
    paper_id: str
    title: str
    abstract: str
    embedding: list[float] | None


@dataclass
class PaperSummary:
    paper_id: str
    title: str
    abstract: str
    matched_by: str | None = None
    score: float | None = None


class PaperSearch:
    def __init__(self) -> None:
        self.database = NEO4J_DATABASE
        self.driver = get_driver()

    def close(self) -> None:
        self.driver.close()

    def get_by_id(self, arxiv_id: str) -> PaperDetails | None:
        records, _, _ = self.driver.execute_query(
            PAPER_BY_ID,
            paper_id=arxiv_id,
            database_=self.database,
            routing_="r",
        )
        if not records:
            return None

        record = records[0]
        return PaperDetails(
            paper_id=record["paper_id"],
            title=record["title"],
            abstract=record["abstract"],
            embedding=record["embedding"],
        )

    def search_by_author(self, name: str, limit: int = 10) -> list[PaperSummary]:
        records, _, _ = self.driver.execute_query(
            PAPERS_BY_AUTHOR,
            normalized_name=normalize_name(name),
            limit=limit,
            database_=self.database,
            routing_="r",
        )
        return [
            PaperSummary(
                paper_id=record["paper_id"],
                title=record["title"],
                abstract=record["abstract"],
                matched_by=record["author_name"],
            )
            for record in records
        ]

    def search_by_category(self, category_code: str, limit: int = 10) -> list[PaperSummary]:
        records, _, _ = self.driver.execute_query(
            PAPERS_BY_CATEGORY,
            category_code=category_code,
            limit=limit,
            database_=self.database,
            routing_="r",
        )
        return [
            PaperSummary(
                paper_id=record["paper_id"],
                title=record["title"],
                abstract=record["abstract"],
            )
            for record in records
        ]

    def search_by_year(
        self, start_year: int, end_year: int | None = None, limit: int = 10
    ) -> list[PaperSummary]:
        records, _, _ = self.driver.execute_query(
            PAPERS_BY_YEAR,
            start_year=start_year,
            end_year=end_year if end_year is not None else start_year,
            limit=limit,
            database_=self.database,
            routing_="r",
        )
        return [
            PaperSummary(
                paper_id=record["paper_id"],
                title=record["title"],
                abstract=record["abstract"],
                matched_by=(
                    str(record["first_submitted_at"].year)
                    if record["first_submitted_at"] is not None
                    else None
                ),
            )
            for record in records
        ]

    def search_fulltext(self, query_text: str, limit: int = 10) -> list[PaperSummary]:
        records, _, _ = self.driver.execute_query(
            FULLTEXT_SEARCH,
            query_text=query_text,
            limit=limit,
            database_=self.database,
            routing_="r",
        )
        return [
            PaperSummary(
                paper_id=record["paper_id"],
                title=record["title"],
                abstract=record["abstract"],
                score=record["score"],
            )
            for record in records
        ]
