import argparse
import logging
import statistics
import subprocess
import time
from pathlib import Path
from typing import Callable

from src.config import NEO4J_DATABASE, get_driver
from src.evaluation.dataset import get_corpus_size, load_eval_queries
from src.evaluation.results_log import append_result
from src.retrieval.graph_expand import GraphExpander
from src.retrieval.search import PaperSearch
from src.retrieval.vector_search import PaperVectorSearch

logger = logging.getLogger(__name__)

EVAL_DIR = Path(__file__).parents[2] / "eval"
PARAPHRASED_PATH = EVAL_DIR / "paraphrased.jsonl"
BENCH_DIR = Path(__file__).parents[2] / "bench"
RESULTS_PATH = BENCH_DIR / "results.jsonl"
CONTAINER_NAME = "neo4j"


def _percentile(values: list[float], pct: float) -> float:
    ranked = sorted(values)
    index = min(len(ranked) - 1, int(len(ranked) * pct))
    return ranked[index]


def _latency_stats(samples: list[float]) -> dict[str, float]:
    if not samples:
        return {"n": 0, "p50_ms": 0.0, "p95_ms": 0.0, "mean_ms": 0.0}
    return {
        "n": len(samples),
        "p50_ms": round(_percentile(samples, 0.50) * 1000, 2),
        "p95_ms": round(_percentile(samples, 0.95) * 1000, 2),
        "mean_ms": round(statistics.mean(samples) * 1000, 2),
    }


def _time_calls(fn: Callable[[str], object], inputs: list[str]) -> list[float]:
    samples = []
    for value in inputs:
        start = time.perf_counter()
        fn(value)
        samples.append(time.perf_counter() - start)
    return samples


def bench_vector_search(queries: list[str], top_k: int) -> dict[str, float]:
    searcher = PaperVectorSearch()
    try:
        samples = _time_calls(lambda q: searcher.search(q, top_k=top_k), queries)
    finally:
        searcher.close()
    return _latency_stats(samples)


def bench_fulltext_search(queries: list[str], top_k: int) -> dict[str, float]:
    searcher = PaperSearch()
    try:
        samples = _time_calls(lambda q: searcher.search_fulltext(q, limit=top_k), queries)
    finally:
        searcher.close()
    return _latency_stats(samples)


def bench_graph_expand(seed_ids: list[str]) -> dict[str, float]:
    expander = GraphExpander()
    try:
        samples = _time_calls(lambda pid: expander.expand([pid]), seed_ids)
    finally:
        expander.close()
    return _latency_stats(samples)


def sample_paper_ids(n: int) -> list[str]:
    driver = get_driver()
    try:
        records, _, _ = driver.execute_query(
            """
            MATCH (p:Paper) WHERE p.embedding IS NOT NULL
            RETURN p.arxiv_id AS id LIMIT $n
            """,
            n=n,
            database_=NEO4J_DATABASE,
            routing_="r",
        )
        return [record["id"] for record in records]
    finally:
        driver.close()


def docker_stats(container: str = CONTAINER_NAME) -> dict[str, str] | None:
    try:
        output = subprocess.run(
            [
                "docker", "stats", container, "--no-stream",
                "--format", "{{.MemUsage}}\t{{.CPUPerc}}",
            ],
            capture_output=True, text=True, check=True, timeout=10,
        ).stdout.strip()
        mem_usage, cpu_percent = output.split("\t")
        return {"mem_usage": mem_usage, "cpu_percent": cpu_percent}
    except (subprocess.CalledProcessError, OSError, ValueError) as error:
        logger.warning("Could not read docker stats for %s: %s", container, error)
        return None


def db_storage_size(container: str = CONTAINER_NAME) -> str | None:
    try:
        output = subprocess.run(
            ["docker", "exec", container, "du", "-sh", "/data/databases/neo4j"],
            capture_output=True, text=True, check=True, timeout=10,
        ).stdout.strip()
        return output.split("\t")[0]
    except (subprocess.CalledProcessError, OSError) as error:
        logger.warning("Could not read DB storage size: %s", error)
        return None


def _print_row(label: str, stats: dict[str, float]) -> None:
    print(f"{label:<20}{stats['n']:>6}{stats['p50_ms']:>12}{stats['p95_ms']:>12}{stats['mean_ms']:>12}")


def cmd_run(args: argparse.Namespace) -> None:
    queries = [q.query for q in load_eval_queries(PARAPHRASED_PATH)][: args.query_sample_size]
    seed_ids = sample_paper_ids(args.graph_sample_size)

    logger.info("Timing vector search over %d queries...", len(queries))
    vector_latency = bench_vector_search(queries, args.top_k)

    logger.info("Timing fulltext search over %d queries...", len(queries))
    fulltext_latency = bench_fulltext_search(queries, args.top_k)

    logger.info("Timing graph expansion over %d seed papers...", len(seed_ids))
    graph_latency = bench_graph_expand(seed_ids)

    driver = get_driver()
    try:
        corpus_size = get_corpus_size(driver, NEO4J_DATABASE)
    finally:
        driver.close()

    resources = docker_stats()
    storage = db_storage_size()

    print(f"\nCorpus size: {corpus_size} papers\n")
    header = f"{'Operation':<20}{'N':>6}{'p50 ms':>12}{'p95 ms':>12}{'mean ms':>12}"
    print(header)
    print("-" * len(header))
    _print_row("vector_search", vector_latency)
    _print_row("fulltext_search", fulltext_latency)
    _print_row("graph_expand", graph_latency)
    print("-" * len(header))

    if resources:
        print(f"Neo4j container: mem={resources['mem_usage']}  cpu={resources['cpu_percent']}")
    if storage:
        print(f"DB storage:      {storage}")

    if not args.no_record:
        append_result(
            RESULTS_PATH,
            {
                "type": "system_performance",
                "corpus_size": corpus_size,
                "top_k": args.top_k,
                "latency": {
                    "vector_search": vector_latency,
                    "fulltext_search": fulltext_latency,
                    "graph_expand": graph_latency,
                },
                "resources": resources,
                "db_storage": storage,
            },
        )
        print(f"\nRecorded to {RESULTS_PATH}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark SciAgent KG operational performance: query latency "
        "(vector/fulltext/graph-expand) and Neo4j container resource usage."
    )
    parser.add_argument(
        "--top-k", type=int, default=10, help="Results fetched per query (default: %(default)s)"
    )
    parser.add_argument(
        "--query-sample-size", type=int, default=20,
        help="Number of paraphrased queries to time (default: %(default)s)",
    )
    parser.add_argument(
        "--graph-sample-size", type=int, default=10,
        help="Number of seed papers to time graph expansion against (default: %(default)s)",
    )
    parser.add_argument(
        "--no-record", action="store_true",
        help=f"Print results without appending to {RESULTS_PATH}",
    )
    parser.add_argument("--log-level", default="INFO", help="Logging level (default: %(default)s)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(message)s")
    cmd_run(args)


if __name__ == "__main__":
    main()
