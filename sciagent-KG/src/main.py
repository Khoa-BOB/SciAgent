import argparse

from src.retrieval.vector_search import PaperVectorSearch


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Search SciAgent papers using vector similarity."
    )
    parser.add_argument(
        "query",
        help="Natural-language research query",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of papers to retrieve",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    searcher = PaperVectorSearch()

    try:
        results = searcher.search(
            query=args.query,
            top_k=args.top_k,
        )

        if not results:
            print("No papers found.")
            return

        for position, result in enumerate(results, start=1):
            print(f"\n{position}. {result.title}")
            print(f"   Paper ID: {result.paper_id}")
            print(f"   Score: {result.score:.4f}")

            abstract_preview = result.abstract.replace("\n", " ")[:300]
            print(f"   Abstract: {abstract_preview}...")

    finally:
        searcher.close()


if __name__ == "__main__":
    main()