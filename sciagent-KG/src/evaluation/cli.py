import argparse
import logging
from dataclasses import asdict
from pathlib import Path

from src.config import NEO4J_DATABASE, get_driver
from src.evaluation.dataset import (
    generate_expansion_cases,
    generate_self_retrieval_queries,
    get_corpus_size,
    load_eval_queries,
    save_eval_queries,
)
from src.evaluation.metrics import EvalSummary, QueryResult, summarize
from src.evaluation.results_log import append_result
from src.retrieval.graph_expand import GraphExpander
from src.retrieval.vector_search import PaperVectorSearch

logger = logging.getLogger(__name__)

EVAL_DIR = Path(__file__).parents[2] / "eval"
SELF_RETRIEVAL_PATH = EVAL_DIR / "self_retrieval.jsonl"
PARAPHRASED_PATH = EVAL_DIR / "paraphrased.jsonl"
RESULTS_PATH = EVAL_DIR / "results.jsonl"
DEFAULT_K_VALUES = (1, 5, 10)
EXPANSION_SOURCES = ("shared_author", "shared_category")


def cmd_generate(args: argparse.Namespace) -> None:
    driver = get_driver()
    try:
        queries = generate_self_retrieval_queries(driver, NEO4J_DATABASE)
    finally:
        driver.close()

    save_eval_queries(queries, args.output)
    logger.info("Wrote %d self-retrieval queries to %s", len(queries), args.output)


def _print_row(label: str, count: int, mrr: float, recall_at: dict[int, float]) -> None:
    recall_str = "".join(f"{recall_at[k]:>10.2%}" for k in DEFAULT_K_VALUES)
    print(f"{label:<20}{count:>6}{mrr:>10.3f}{recall_str}")


def _report(
    results_by_source: dict[str, list[QueryResult]],
) -> tuple[dict[str, EvalSummary], EvalSummary]:
    """Print the Source/N/MRR/Recall@k table and return per-source + overall summaries."""
    header = f"{'Source':<20}{'N':>6}{'MRR':>10}" + "".join(
        f"{'R@' + str(k):>10}" for k in DEFAULT_K_VALUES
    )
    print(f"\n{header}")
    print("-" * len(header))

    summaries: dict[str, EvalSummary] = {}
    all_results: list[QueryResult] = []
    for source in sorted(results_by_source):
        results = results_by_source[source]
        all_results.extend(results)
        summary = summarize(results, DEFAULT_K_VALUES)
        summaries[source] = summary
        _print_row(source, summary.count, summary.mrr, summary.recall_at)

    print("-" * len(header))
    overall = summarize(all_results, DEFAULT_K_VALUES)
    _print_row("TOTAL", overall.count, overall.mrr, overall.recall_at)

    return summaries, overall


def cmd_run(args: argparse.Namespace) -> None:
    eval_files = args.eval_file or [SELF_RETRIEVAL_PATH, PARAPHRASED_PATH]

    queries = []
    for path in eval_files:
        if not path.exists():
            logger.warning("Eval file not found, skipping: %s", path)
            continue
        queries.extend(load_eval_queries(path))

    if not queries:
        print(
            "No eval queries found. Run 'generate' first for self-retrieval, "
            "or pass --eval-file."
        )
        return

    searcher = PaperVectorSearch()
    results_by_source: dict[str, list[QueryResult]] = {}
    try:
        for eval_query in queries:
            query_embedding = searcher.embed_query(eval_query.query)
            hits = searcher.search_by_embedding(query_embedding, top_k=args.top_k)
            results_by_source.setdefault(eval_query.source, []).append(
                QueryResult(
                    query=eval_query.query,
                    expected_paper_id=eval_query.expected_paper_id,
                    source=eval_query.source,
                    ranked_ids=[hit.paper_id for hit in hits],
                )
            )
    finally:
        searcher.close()

    summaries, overall = _report(results_by_source)

    if args.record:
        driver = get_driver()
        try:
            corpus_size = get_corpus_size(driver, NEO4J_DATABASE)
        finally:
            driver.close()

        append_result(
            RESULTS_PATH,
            {
                "type": "retrieval_quality",
                "corpus_size": corpus_size,
                "top_k": args.top_k,
                "by_source": {source: asdict(summary) for source, summary in summaries.items()},
                "total": asdict(overall),
            },
        )
        print(f"\nRecorded to {RESULTS_PATH}")


def cmd_expand(args: argparse.Namespace) -> None:
    """Evaluate GraphExpander against auto-generated shared-author/shared-category
    pairs: for each seed paper, does expand() surface a paper known to be
    connected to it (same author or same category) within top-k?
    """
    driver = get_driver()
    try:
        cases = []
        for source in EXPANSION_SOURCES:
            cases.extend(
                generate_expansion_cases(driver, NEO4J_DATABASE, source, limit=args.limit)
            )
    finally:
        driver.close()

    if not cases:
        print(
            "No expansion cases found -- need authors/categories with >=2 "
            "embedded papers. Has embedding finished for enough of the corpus?"
        )
        return

    expander = GraphExpander()
    results_by_source: dict[str, list[QueryResult]] = {}
    try:
        for case in cases:
            expanded = expander.expand(
                [case.seed_id],
                query_embedding=case.seed_embedding if args.use_embedding else None,
                related_limit=args.top_k,
                pool_size=args.pool_size,
            )
            results_by_source.setdefault(case.source, []).append(
                QueryResult(
                    query=case.seed_id,
                    expected_paper_id=case.expected_id,
                    source=case.source,
                    ranked_ids=[related.paper_id for related in expanded.related_papers],
                )
            )
    finally:
        expander.close()

    summaries, overall = _report(results_by_source)

    if args.record:
        driver = get_driver()
        try:
            corpus_size = get_corpus_size(driver, NEO4J_DATABASE)
        finally:
            driver.close()

        append_result(
            RESULTS_PATH,
            {
                "type": "graph_expansion_quality",
                "corpus_size": corpus_size,
                "top_k": args.top_k,
                "pool_size": args.pool_size,
                "use_embedding": args.use_embedding,
                "by_source": {source: asdict(summary) for source, summary in summaries.items()},
                "total": asdict(overall),
            },
        )
        print(f"\nRecorded to {RESULTS_PATH}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate SciAgent retrieval quality.")
    parser.add_argument(
        "--log-level", default="INFO", help="Logging level (default: %(default)s)"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate_parser = subparsers.add_parser(
        "generate", help="Build the self-retrieval eval set from the live graph."
    )
    generate_parser.add_argument(
        "--output",
        type=Path,
        default=SELF_RETRIEVAL_PATH,
        help=f"Output path (default: {SELF_RETRIEVAL_PATH})",
    )

    run_parser = subparsers.add_parser(
        "run", help="Run vector search against eval queries and report Recall@k / MRR."
    )
    run_parser.add_argument(
        "--eval-file",
        type=Path,
        action="append",
        default=None,
        help="Eval JSONL file(s) to run (default: self_retrieval.jsonl + paraphrased.jsonl)",
    )
    run_parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="How many results to fetch per query (default: %(default)s)",
    )
    run_parser.add_argument(
        "--record",
        action="store_true",
        help=f"Append this run's results (with timestamp + git commit) to {RESULTS_PATH}",
    )

    expand_parser = subparsers.add_parser(
        "expand",
        help="Evaluate GraphExpander against auto-generated shared-author/"
        "shared-category pairs (Recall@k / MRR for surfacing known-connected papers).",
    )
    expand_parser.add_argument(
        "--limit",
        type=int,
        default=500,
        help="Max cases per source (default: %(default)s)",
    )
    expand_parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="related_limit passed to GraphExpander.expand (default: %(default)s)",
    )
    expand_parser.add_argument(
        "--pool-size",
        type=int,
        default=20,
        help="pool_size passed to GraphExpander.expand (default: %(default)s)",
    )
    expand_parser.add_argument(
        "--no-embedding",
        dest="use_embedding",
        action="store_false",
        help="Rank by graph structure only (shared author/category counts), "
        "matching expand()'s behavior when no query embedding is available.",
    )
    expand_parser.set_defaults(use_embedding=True)
    expand_parser.add_argument(
        "--record",
        action="store_true",
        help=f"Append this run's results (with timestamp + git commit) to {RESULTS_PATH}",
    )

    return parser.parse_args()


COMMANDS = {"generate": cmd_generate, "run": cmd_run, "expand": cmd_expand}


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=args.log_level, format="%(asctime)s %(levelname)s %(message)s"
    )
    COMMANDS[args.command](args)


if __name__ == "__main__":
    main()
