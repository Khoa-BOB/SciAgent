import argparse
import logging
from pathlib import Path

from src.config import NEO4J_DATABASE, get_driver
from src.evaluation.dataset import (
    generate_self_retrieval_queries,
    load_eval_queries,
    save_eval_queries,
)
from src.evaluation.metrics import QueryResult, summarize
from src.retrieval.vector_search import PaperVectorSearch

logger = logging.getLogger(__name__)

EVAL_DIR = Path(__file__).parents[2] / "eval"
SELF_RETRIEVAL_PATH = EVAL_DIR / "self_retrieval.jsonl"
PARAPHRASED_PATH = EVAL_DIR / "paraphrased.jsonl"
DEFAULT_K_VALUES = (1, 5, 10)


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

    header = f"{'Source':<20}{'N':>6}{'MRR':>10}" + "".join(
        f"{'R@' + str(k):>10}" for k in DEFAULT_K_VALUES
    )
    print(f"\n{header}")
    print("-" * len(header))

    all_results: list[QueryResult] = []
    for source in sorted(results_by_source):
        results = results_by_source[source]
        all_results.extend(results)
        summary = summarize(results, DEFAULT_K_VALUES)
        _print_row(source, summary.count, summary.mrr, summary.recall_at)

    print("-" * len(header))
    overall = summarize(all_results, DEFAULT_K_VALUES)
    _print_row("TOTAL", overall.count, overall.mrr, overall.recall_at)


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

    return parser.parse_args()


COMMANDS = {"generate": cmd_generate, "run": cmd_run}


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=args.log_level, format="%(asctime)s %(levelname)s %(message)s"
    )
    COMMANDS[args.command](args)


if __name__ == "__main__":
    main()
