import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from tqdm import tqdm

from src.extraction.candidates import DEFAULT_SPACY_MODEL, extract_candidates, load_model
from src.extraction.llm_client import ExtractionClient
from src.ingestion.checkpoint import load_checkpoint, save_checkpoint

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "qwen3.5"
DEFAULT_BASE_URL = "http://localhost:11434/v1"  # Ollama's OpenAI-compatible endpoint


def read_shard(shard_path: Path) -> list[dict]:
    papers = []
    with shard_path.open(encoding="utf-8") as shard_file:
        for line in shard_file:
            line = line.strip()
            if line:
                papers.append(json.loads(line))
    return papers


def run_extraction(
    shard_path: Path,
    output_path: Path,
    client: ExtractionClient,
    spacy_model: str = DEFAULT_SPACY_MODEL,
    resume: bool = True,
) -> int:
    papers = read_shard(shard_path)

    start_index = 0
    if resume:
        checkpoint = load_checkpoint(shard_path)
        if checkpoint is not None:
            start_index = checkpoint.last_line
            logger.info("Resuming %s from paper %d/%d", shard_path.name, start_index, len(papers))

    nlp = load_model(spacy_model)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if start_index > 0 else "w"

    processed = 0
    with output_path.open(mode, encoding="utf-8") as output_file:
        for index in tqdm(
            range(start_index, len(papers)), initial=start_index, total=len(papers),
            desc=shard_path.name, unit="paper",
        ):
            paper = papers[index]
            candidates = extract_candidates(paper["abstract"], nlp)
            entities = client.extract(paper["title"], paper["abstract"], candidates)

            record = {
                "paper_id": paper["arxiv_id"],
                "entities": [{"name": e.name, "type": e.type} for e in entities],
                "extraction_model": client.model,
                "extracted_at": datetime.now(timezone.utc).isoformat(),
            }
            output_file.write(json.dumps(record, ensure_ascii=False) + "\n")
            output_file.flush()

            save_checkpoint(shard_path, index + 1, paper["arxiv_id"])
            processed += 1

    return processed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stage A+B: spaCy candidates + LLM structured extraction "
        "for one shard. Works identically against a local Ollama server "
        "(--base-url http://localhost:11434/v1) or a vLLM OpenAI-compatible "
        "server on HPC (--base-url http://localhost:8000/v1)."
    )
    parser.add_argument("shard", type=Path, help="Input shard JSONL (from src.extraction.export)")
    parser.add_argument(
        "--output", type=Path, default=None,
        help="Output JSONL path (default: <shard>.extracted.jsonl next to the shard)",
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="OpenAI-compatible API base URL (default: %(default)s)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model name as served by the backend (default: %(default)s)")
    parser.add_argument("--api-key", default="not-needed", help="API key, if the backend requires one")
    parser.add_argument("--spacy-model", default=DEFAULT_SPACY_MODEL, help="spaCy model for candidate extraction (default: %(default)s)")
    parser.add_argument("--no-resume", action="store_true", help="Ignore any existing checkpoint and reprocess the whole shard")
    parser.add_argument("--log-level", default="INFO", help="Logging level (default: %(default)s)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(message)s")

    output_path = args.output or args.shard.with_suffix(".extracted.jsonl")
    client = ExtractionClient(base_url=args.base_url, model=args.model, api_key=args.api_key)

    processed = run_extraction(
        args.shard, output_path, client,
        spacy_model=args.spacy_model, resume=not args.no_resume,
    )
    logger.info("Extracted %d paper(s) from %s into %s", processed, args.shard, output_path)


if __name__ == "__main__":
    main()
