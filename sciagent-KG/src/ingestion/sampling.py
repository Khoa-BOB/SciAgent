import argparse
import json
import logging
import random
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_INPUT_PATH = Path(__file__).parents[3] / "data/csAI/cs_ai_papers.jsonl"
DEFAULT_OUTPUT_DIR = Path(__file__).parents[3] / "data/example"
DEFAULT_N = 500
DEFAULT_SEED = 42


def reservoir_sample(input_path: Path, n: int, seed: int) -> list[str]:
    """Single-pass, deterministic reservoir sampling (Algorithm R) of n raw JSONL
    lines from input_path. O(n) memory regardless of input file size, and always
    picks the same n lines for a given (input_path content, n, seed) — this is
    what makes a sample reproducible without re-running against the full 190K-line
    corpus every time.
    """
    rng = random.Random(seed)
    reservoir: list[str] = []
    seen = 0

    with input_path.open("r", encoding="utf-8") as infile:
        for line_number, line in enumerate(infile, start=1):
            if not line.strip():
                continue

            try:
                json.loads(line)
            except json.JSONDecodeError:
                logger.warning("Skipping invalid JSON on line %d", line_number)
                continue

            if seen < n:
                reservoir.append(line)
            else:
                j = rng.randint(0, seen)
                if j < n:
                    reservoir[j] = line
            seen += 1

    if seen < n:
        logger.warning(
            "Requested %d papers but only %d eligible records found in %s",
            n,
            seen,
            input_path,
        )

    return reservoir


def write_sample(sample: list[str], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as outfile:
        for line in sample:
            outfile.write(line.rstrip("\n") + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Deterministically sample N papers from the full cs.AI "
        "corpus for local development, without loading the whole 190K-paper "
        "file into the graph."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT_PATH,
        help=f"Source JSONL file (default: {DEFAULT_INPUT_PATH})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output JSONL file (default: data/example/sample_<n>.jsonl)",
    )
    parser.add_argument(
        "--n",
        type=int,
        default=DEFAULT_N,
        help="Number of papers to sample (default: %(default)s)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help="Random seed for reproducibility (default: %(default)s)",
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

    output_path = args.output or DEFAULT_OUTPUT_DIR / f"sample_{args.n}.jsonl"

    sample = reservoir_sample(args.input, args.n, args.seed)
    write_sample(sample, output_path)

    logger.info(
        "Sampled %d paper(s) from %s (seed=%d) into %s",
        len(sample),
        args.input,
        args.seed,
        output_path,
    )


if __name__ == "__main__":
    main()
