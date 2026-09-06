import argparse

from src.extraction.extract import DEFAULT_BASE_URL, DEFAULT_MODEL
from src.extraction.llm_client import resolve_api_key
from src.retrieval.graph_expand import ExpandedResult, GraphExpander
from src.retrieval.hybrid_search import PaperHybridSearch
from src.retrieval.nl_query import NLGraphQuery, build_default_llm
from src.retrieval.search import PaperSearch, PaperSummary
from src.retrieval.vector_search import PaperVectorSearch


def _print_seed(
    paper_id: str,
    title: str,
    abstract: str,
    expanded: ExpandedResult | None,
    position: int | None = None,
    score: float | None = None,
) -> None:
    heading = f"\n{position}. {title}" if position is not None else f"\n{title}"
    print(heading)
    print(f"   Paper ID: {paper_id}")
    if score is not None:
        print(f"   Score: {score:.4f}")

    abstract_preview = (abstract or "").replace("\n", " ")[:300]
    print(f"   Abstract: {abstract_preview}...")

    if expanded is not None:
        context = expanded.seed_context.get(paper_id)
        if context is not None:
            print(f"   Authors: {', '.join(context.authors)}")
            print(f"   Categories: {', '.join(context.categories)}")


def _print_related(expanded: ExpandedResult) -> None:
    if not expanded.related_papers:
        return

    print("\n=== Related papers (graph expansion) ===")
    for related in expanded.related_papers:
        reasons = []
        if related.shared_authors:
            reasons.append(f"authors: {', '.join(related.shared_authors)}")
        if related.shared_categories:
            reasons.append(f"categories: {', '.join(related.shared_categories)}")
        reasons.append(f"similarity: {related.similarity_to_query:.4f}")
        print(f"   - {related.title} [{related.paper_id}] ({'; '.join(reasons)})")


def _print_summaries(
    results: list[PaperSummary], header: str, matched_label: str = "Matched"
) -> None:
    if not results:
        print("No papers found.")
        return

    print(f"\n=== {header} ===")
    for position, result in enumerate(results, start=1):
        print(f"\n{position}. {result.title}")
        print(f"   Paper ID: {result.paper_id}")
        if result.matched_by:
            print(f"   {matched_label}: {result.matched_by}")
        if result.score is not None:
            print(f"   Score: {result.score:.4f}")

        abstract_preview = (result.abstract or "").replace("\n", " ")[:300]
        print(f"   Abstract: {abstract_preview}...")


def cmd_search(args: argparse.Namespace) -> None:
    searcher = PaperVectorSearch()
    expander = None if args.no_expand else GraphExpander()

    try:
        query_embedding = searcher.embed_query(args.query)
        results = searcher.search_by_embedding(query_embedding, top_k=args.top_k)

        if not results:
            print("No papers found.")
            return

        expanded = None
        if expander is not None:
            expanded = expander.expand(
                paper_ids=[result.paper_id for result in results],
                query_embedding=query_embedding,
                related_limit=args.related_limit,
            )

        print(f"\n=== Seed papers (top-{args.top_k} by vector similarity) ===")
        for position, result in enumerate(results, start=1):
            _print_seed(
                result.paper_id,
                result.title,
                result.abstract,
                expanded,
                position=position,
                score=result.score,
            )

        if expanded is not None:
            _print_related(expanded)
    finally:
        searcher.close()
        if expander is not None:
            expander.close()


def cmd_by_id(args: argparse.Namespace) -> None:
    search = PaperSearch()
    expander = None if args.no_expand else GraphExpander()

    try:
        paper = search.get_by_id(args.arxiv_id)
        if paper is None:
            print(f"No paper found with arxiv_id={args.arxiv_id!r}")
            return

        expanded = None
        if expander is not None:
            expanded = expander.expand(
                paper_ids=[paper.paper_id],
                query_embedding=paper.embedding,
                related_limit=args.related_limit,
            )

        print("=== Paper ===")
        _print_seed(paper.paper_id, paper.title, paper.abstract, expanded)

        if expanded is not None:
            _print_related(expanded)
    finally:
        search.close()
        if expander is not None:
            expander.close()


def cmd_by_author(args: argparse.Namespace) -> None:
    search = PaperSearch()
    try:
        results = search.search_by_author(args.name, limit=args.limit)
        _print_summaries(
            results, f"Papers by author matching {args.name!r}", matched_label="Author"
        )
    finally:
        search.close()


def cmd_by_category(args: argparse.Namespace) -> None:
    search = PaperSearch()
    try:
        results = search.search_by_category(args.category_code, limit=args.limit)
        _print_summaries(results, f"Papers in category {args.category_code!r}")
    finally:
        search.close()


def cmd_by_year(args: argparse.Namespace) -> None:
    search = PaperSearch()
    try:
        results = search.search_by_year(
            args.year, end_year=args.to, limit=args.limit
        )
        header = (
            f"Papers submitted in {args.year}"
            if args.to is None
            else f"Papers submitted {args.year}-{args.to}"
        )
        _print_summaries(results, header, matched_label="Year")
    finally:
        search.close()


def cmd_fulltext(args: argparse.Namespace) -> None:
    search = PaperSearch()
    try:
        results = search.search_fulltext(args.query, limit=args.limit)
        _print_summaries(results, f"Fulltext matches for {args.query!r}")
    finally:
        search.close()


def cmd_hybrid(args: argparse.Namespace) -> None:
    search = PaperHybridSearch()
    try:
        results = search.search(args.query, top_k=args.top_k)
        summaries = [
            PaperSummary(
                paper_id=r.paper_id, title=r.title, abstract=r.abstract, score=r.score
            )
            for r in results
        ]
        _print_summaries(summaries, f"Hybrid (vector + fulltext) matches for {args.query!r}")
    finally:
        search.close()


def cmd_nl_query(args: argparse.Namespace) -> None:
    llm = build_default_llm(
        base_url=args.base_url,
        model=args.model,
        api_key=resolve_api_key(args.api_key, args.base_url),
    )
    nl_query = NLGraphQuery(llm=llm)
    try:
        result = nl_query.query(args.question)
        print(f"\nGenerated Cypher:\n  {result.metadata.get('cypher')}\n")
        if not result.items:
            print("No results.")
            return
        print(f"=== Results ({len(result.items)}) ===")
        for position, item in enumerate(result.items, start=1):
            print(f"{position}. {item.content}")
    finally:
        nl_query.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search SciAgent papers.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    search_parser = subparsers.add_parser(
        "search", help="Semantic (vector similarity) search."
    )
    search_parser.add_argument("query", help="Natural-language research query")
    search_parser.add_argument(
        "--top-k", type=int, default=5, help="Number of papers to retrieve"
    )
    search_parser.add_argument(
        "--related-limit",
        type=int,
        default=5,
        help="Number of related papers to surface via graph expansion",
    )
    search_parser.add_argument(
        "--no-expand",
        action="store_true",
        help="Skip graph expansion (authors, categories, related papers)",
    )

    by_id_parser = subparsers.add_parser(
        "by-id", help="Look up a paper by arxiv_id and show related papers."
    )
    by_id_parser.add_argument("arxiv_id", help="arXiv identifier, e.g. 0903.0174")
    by_id_parser.add_argument(
        "--related-limit",
        type=int,
        default=5,
        help="Number of related papers to surface via graph expansion",
    )
    by_id_parser.add_argument(
        "--no-expand",
        action="store_true",
        help="Skip graph expansion (authors, categories, related papers)",
    )

    by_author_parser = subparsers.add_parser(
        "by-author", help="Find papers by author name."
    )
    by_author_parser.add_argument("name", help="Author name or partial name")
    by_author_parser.add_argument(
        "--limit", type=int, default=10, help="Max papers to return"
    )

    by_category_parser = subparsers.add_parser(
        "by-category", help="List papers in a category."
    )
    by_category_parser.add_argument(
        "category_code", help="arXiv category code, e.g. cs.CL"
    )
    by_category_parser.add_argument(
        "--limit", type=int, default=10, help="Max papers to return"
    )

    by_year_parser = subparsers.add_parser(
        "by-year", help="List papers first submitted in a year or year range."
    )
    by_year_parser.add_argument("year", type=int, help="Start year, e.g. 2020")
    by_year_parser.add_argument(
        "--to",
        type=int,
        default=None,
        help="End year (inclusive) for a range; omit for a single year",
    )
    by_year_parser.add_argument(
        "--limit", type=int, default=10, help="Max papers to return"
    )

    fulltext_parser = subparsers.add_parser(
        "fulltext", help="Exact-keyword search over title/abstract."
    )
    fulltext_parser.add_argument("query", help="Keywords to search for")
    fulltext_parser.add_argument(
        "--limit", type=int, default=10, help="Max papers to return"
    )

    hybrid_parser = subparsers.add_parser(
        "hybrid", help="Combined vector + fulltext search."
    )
    hybrid_parser.add_argument("query", help="Natural-language or keyword query")
    hybrid_parser.add_argument(
        "--top-k", type=int, default=5, help="Number of papers to retrieve"
    )

    nl_query_parser = subparsers.add_parser(
        "nl-query",
        help="Natural-language graph query, converted to read-only Cypher by an LLM.",
    )
    nl_query_parser.add_argument("question", help="Natural-language question about the graph")
    nl_query_parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help="OpenAI-compatible API base URL (default: %(default)s, i.e. local Ollama)",
    )
    nl_query_parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="Model name as served by the backend (default: %(default)s)",
    )
    nl_query_parser.add_argument(
        "--api-key",
        default=None,
        help="API key. Defaults to OPENAI_API_KEY in sciagent-KG/.env when --base-url "
        "points at api.openai.com; avoid passing a real key here directly (visible in "
        "`ps`/process listings).",
    )

    return parser.parse_args()


COMMANDS = {
    "search": cmd_search,
    "by-id": cmd_by_id,
    "by-author": cmd_by_author,
    "by-category": cmd_by_category,
    "by-year": cmd_by_year,
    "fulltext": cmd_fulltext,
    "hybrid": cmd_hybrid,
    "nl-query": cmd_nl_query,
}


def main() -> None:
    args = parse_args()
    COMMANDS[args.command](args)


if __name__ == "__main__":
    main()
