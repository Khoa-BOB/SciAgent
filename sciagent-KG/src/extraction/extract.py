import argparse
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from tqdm import tqdm

from src.extraction.candidates import DEFAULT_SPACY_MODEL, extract_candidates, load_model
from src.extraction.llm_client import ExtractionClient, resolve_api_key
from src.ingestion.checkpoint import load_checkpoint, save_checkpoint

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "zephyr:latest"  # non-reasoning model -- qwen3.5's "thinking" mode
# burns its whole context on chain-of-thought and never emits structured output in time.
DEFAULT_BASE_URL = "http://localhost:11434/v1"  # Ollama's OpenAI-compatible endpoint
DEFAULT_CONCURRENCY = 1  # sequential by default; HPC/vLLM runs should raise this a lot --
# vLLM's throughput comes from batching concurrent requests, a single in-flight
# request at a time leaves most of the GPU idle.
DEFAULT_BATCH_SIZE = 1  # papers packed into one LLM request; >1 cuts total request
# count roughly proportionally -- the fix for a requests/day cap (not a token cap),
# confirmed hit at 10k gpt-4o-mini requests/day on this pipeline.


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
    concurrency: int = DEFAULT_CONCURRENCY,
    batch_size: int = DEFAULT_BATCH_SIZE,
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
    pending = papers[start_index:]
    batches = [pending[i : i + batch_size] for i in range(0, len(pending), batch_size)]

    def _extract_batch(batch: list[dict]) -> list[list]:
        inputs = [
            (paper["title"], paper["abstract"], extract_candidates(paper["abstract"], nlp))
            for paper in batch
        ]
        # Single-paper batches go through extract() unchanged (same prompt/schema
        # already validated) rather than wrapping a batch-of-one through
        # extract_batch()'s different prompt shape.
        if len(inputs) == 1:
            return [client.extract(*inputs[0])]
        return client.extract_batch(inputs)

    processed = 0
    with output_path.open(mode, encoding="utf-8") as output_file, \
         ThreadPoolExecutor(max_workers=concurrency) as executor:
        # executor.map yields results in input order even though the calls
        # themselves run concurrently, so checkpointing stays as simple as
        # strictly-sequential "everything up to index N is done" -- per
        # paper, even though the LLM calls happen per batch.
        batch_results = executor.map(_extract_batch, batches)
        progress = tqdm(total=len(papers), initial=start_index, desc=shard_path.name, unit="paper")
        index = start_index
        for batch, entities_per_paper in zip(batches, batch_results):
            for paper, entities in zip(batch, entities_per_paper):
                record = {
                    "paper_id": paper["arxiv_id"],
                    "entities": [{"name": e.name, "type": e.type} for e in entities],
                    "extraction_model": client.model,
                    "extracted_at": datetime.now(timezone.utc).isoformat(),
                }
                output_file.write(json.dumps(record, ensure_ascii=False) + "\n")
                output_file.flush()

                save_checkpoint(shard_path, index + 1, paper["arxiv_id"])
                index += 1
                processed += 1

                usage = client.usage
                progress.set_postfix(
                    tokens=f"{usage.total_tokens:,}", requests=usage.requests, refresh=False
                )
                progress.update(1)
        progress.close()

    usage = client.usage
    logger.info(
        "%s: %d request(s), %s input token(s), %s output token(s), %s total",
        shard_path.name, usage.requests,
        f"{usage.input_tokens:,}", f"{usage.output_tokens:,}", f"{usage.total_tokens:,}",
    )
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
    parser.add_argument(
        "--api-key", default=None,
        help="API key. Defaults to OPENAI_API_KEY in sciagent-KG/.env when --base-url "
        "is an OpenAI endpoint (Ollama/vLLM don't need one). Avoid passing this "
        "explicitly -- it leaks into `ps`/process listings.",
    )
    parser.add_argument("--spacy-model", default=DEFAULT_SPACY_MODEL, help="spaCy model for candidate extraction (default: %(default)s)")
    parser.add_argument(
        "--concurrency", type=int, default=DEFAULT_CONCURRENCY,
        help="Batches in flight at once (default: %(default)s, i.e. sequential). "
        "Raise a lot for vLLM/HPC runs -- vLLM batches concurrent requests "
        "server-side; a single in-flight request leaves most of the GPU idle.",
    )
    parser.add_argument(
        "--papers-per-request", type=int, default=DEFAULT_BATCH_SIZE, dest="batch_size",
        help="Papers packed into one LLM request (default: %(default)s). Raise this "
        "to cut total request count for providers with a requests/day cap rather "
        "than a token cap (e.g. OpenAI) -- concurrency controls requests in "
        "flight, this controls papers per request; total requests for a shard "
        "is roughly shard_size / this value.",
    )
    parser.add_argument(
        "--no-thinking-hint", dest="thinking_hint", action="store_false",
        help="Skip the chat_template_kwargs thinking-disable hint -- use for hosted "
        "APIs like OpenAI that don't recognize it and aren't reasoning models anyway.",
    )
    parser.add_argument("--no-resume", action="store_true", help="Ignore any existing checkpoint and reprocess the whole shard")
    parser.add_argument("--log-level", default="INFO", help="Logging level (default: %(default)s)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(message)s")

    output_path = args.output or args.shard.with_suffix(".extracted.jsonl")
    client = ExtractionClient(
        base_url=args.base_url, model=args.model,
        api_key=resolve_api_key(args.api_key, args.base_url),
        thinking_hint=args.thinking_hint,
    )

    processed = run_extraction(
        args.shard, output_path, client,
        spacy_model=args.spacy_model, resume=not args.no_resume,
        concurrency=args.concurrency, batch_size=args.batch_size,
    )
    logger.info("Extracted %d paper(s) from %s into %s", processed, args.shard, output_path)


if __name__ == "__main__":
    main()
