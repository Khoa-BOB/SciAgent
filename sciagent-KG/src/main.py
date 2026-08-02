import argparse

from src.retrieval.graph_expand import GraphExpander
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
    parser.add_argument(
        "--no-expand",
        action="store_true",
        help="Skip graph expansion (authors, categories, related papers)",
    )
    parser.add_argument(
        "--related-limit",
        type=int,
        default=5,
        help="Number of related papers to surface via graph expansion",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    searcher = PaperVectorSearch()
    expander = None if args.no_expand else GraphExpander()

    try:
        query_embedding = searcher.embed_query(args.query)
        results = searcher.search_by_embedding(
            query_embedding=query_embedding,
            top_k=args.top_k,
        )

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
            print(f"\n{position}. {result.title}")
            print(f"   Paper ID: {result.paper_id}")
            print(f"   Score: {result.score:.4f}")

            abstract_preview = result.abstract.replace("\n", " ")[:300]
            print(f"   Abstract: {abstract_preview}...")

            if expanded is not None:
                context = expanded.seed_context.get(result.paper_id)
                if context is not None:
                    print(f"   Authors: {', '.join(context.authors)}")
                    print(f"   Categories: {', '.join(context.categories)}")

        if expanded is not None and expanded.related_papers:
            print("\n=== Related papers (graph expansion, not in seed results) ===")
            for related in expanded.related_papers:
                reasons = []
                if related.shared_authors:
                    reasons.append(f"authors: {', '.join(related.shared_authors)}")
                if related.shared_categories:
                    reasons.append(
                        f"categories: {', '.join(related.shared_categories)}"
                    )
                reasons.append(f"similarity: {related.similarity_to_query:.4f}")
                print(f"   - {related.title} [{related.paper_id}] ({'; '.join(reasons)})")

    finally:
        searcher.close()
        if expander is not None:
            expander.close()


if __name__ == "__main__":
    main()