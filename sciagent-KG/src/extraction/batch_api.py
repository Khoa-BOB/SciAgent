"""OpenAI Batch API path for entity extraction.

Separate quota bucket from the synchronous chat-completions API (which this
pipeline hit a 10k-requests/day cap on), 50% cheaper, and reuses the exact
same single-paper SYSTEM_PROMPT/EXTRACTION_SCHEMA/build_user_prompt as
llm_client.ExtractionClient.extract() -- unlike prompt-side batching
(--papers-per-request > 1), there's no quality tradeoff here, since every
request is still one paper.

OpenAI-specific by nature (Batches is not an Ollama/vLLM-compatible
endpoint), so unlike llm_client.py this isn't backend-agnostic.

Three phases, run as separate commands since a batch can take up to 24h:
  submit  -- find papers needing extraction, upload a batch request file, start the job
  status  -- check progress
  collect -- once complete, download results into shards_dir/batch_recovery.extracted.jsonl
"""

import argparse
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from openai import OpenAI
from tqdm import tqdm

from src.extraction.candidates import DEFAULT_SPACY_MODEL, extract_candidates, load_model
from src.extraction.export import DEFAULT_OUTPUT_DIR as DEFAULT_SHARDS_DIR
from src.extraction.llm_client import (  # also runs llm_client's load_dotenv() on import
    EXTRACTION_SCHEMA,
    MAX_COMPLETION_TOKENS,
    SYSTEM_PROMPT,
    build_user_prompt,
)

logger = logging.getLogger(__name__)


def _resolve_api_key(explicit: str | None) -> str:
    """Prefer .env over a CLI flag -- a key passed as --api-key is visible
    in `ps`/process listings to any local user."""
    key = explicit or os.environ.get("OPENAI_API_KEY")
    if not key:
        raise SystemExit(
            "No OpenAI API key found. Add it to sciagent-KG/.env as:\n"
            "  OPENAI_API_KEY=sk-...\n"
            "(avoid --api-key on the command line -- it leaks into `ps`/process listings)"
        )
    return key


DEFAULT_MODEL = "gpt-4o-mini"
# OpenAI caps total enqueued tokens across in-flight batches per account/model
# tier (hit at 2,000,000 on this account submitting all 24,090 papers in one
# batch -- the whole submission was rejected, nothing processed). ~700
# tokens/request observed; 1500/chunk leaves a healthy margin.
DEFAULT_CHUNK_SIZE = 1500
DEFAULT_POLL_INTERVAL = 60


def _state_path(shards_dir: Path) -> Path:
    return shards_dir / "batch_job.json"


def papers_needing_extraction(shards_dir: Path) -> list[dict]:
    """Papers with no successful extraction yet -- either never attempted,
    or attempted but came back empty (rate-limit exhaustion, parse failure).
    Safe to call repeatedly; recomputed fresh from the current file state.
    """
    already_ok: set[str] = set()
    for extracted_path in shards_dir.glob("*.extracted.jsonl"):
        with extracted_path.open(encoding="utf-8") as extracted_file:
            for line in extracted_file:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                if record["entities"]:
                    already_ok.add(record["paper_id"])

    papers: list[dict] = []
    seen: set[str] = set()
    for shard_path in sorted(shards_dir.glob("shard_*.jsonl")):
        if shard_path.name.endswith(".extracted.jsonl"):
            continue
        with shard_path.open(encoding="utf-8") as shard_file:
            for line in shard_file:
                line = line.strip()
                if not line:
                    continue
                paper = json.loads(line)
                if paper["arxiv_id"] not in already_ok and paper["arxiv_id"] not in seen:
                    seen.add(paper["arxiv_id"])
                    papers.append(paper)
    return papers


def build_batch_requests(papers: list[dict], model: str, spacy_model: str) -> list[dict]:
    nlp = load_model(spacy_model)
    requests = []
    for paper in tqdm(papers, desc="Building candidates", unit="paper"):
        candidates = extract_candidates(paper["abstract"], nlp)
        requests.append({
            "custom_id": paper["arxiv_id"],
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": {
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": build_user_prompt(paper["title"], paper["abstract"], candidates)},
                ],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": "extraction", "schema": EXTRACTION_SCHEMA, "strict": True},
                },
                "temperature": 0,
                "max_tokens": MAX_COMPLETION_TOKENS,
            },
        })
    return requests


def _submit_chunk(
    client: OpenAI, papers: list[dict], model: str, spacy_model: str,
    shards_dir: Path, label: str,
):
    requests = build_batch_requests(papers, model, spacy_model)

    batch_input_path = shards_dir / f"batch_input_{label}.jsonl"
    with batch_input_path.open("w", encoding="utf-8") as input_file:
        for request in requests:
            input_file.write(json.dumps(request, ensure_ascii=False) + "\n")
    logger.info("Wrote %d request(s) to %s", len(requests), batch_input_path)

    with batch_input_path.open("rb") as upload_file:
        uploaded = client.files.create(file=upload_file, purpose="batch")

    batch = client.batches.create(
        input_file_id=uploaded.id,
        endpoint="/v1/chat/completions",
        completion_window="24h",
    )
    logger.info("Submitted batch %s (%d requests, chunk %s)", batch.id, len(requests), label)
    return batch


def _write_results(content: str, model: str, output_path: Path) -> int:
    written = 0
    with output_path.open("w", encoding="utf-8") as output_file:
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            result = json.loads(line)
            paper_id = result["custom_id"]
            entities: list[dict] = []

            response = result.get("response")
            if response and response.get("status_code") == 200:
                message_content = response["body"]["choices"][0]["message"]["content"]
                try:
                    payload = json.loads(message_content)
                    entities = [
                        {"name": e["name"], "type": e["type"]}
                        for e in payload.get("entities", [])
                        if e.get("name") and e.get("type") in ("method", "dataset", "topic")
                    ]
                except (json.JSONDecodeError, KeyError, TypeError) as error:
                    logger.warning("Could not parse batch result for %s: %s", paper_id, error)
            else:
                logger.warning("Batch request failed for %s: %s", paper_id, result.get("error"))

            record = {
                "paper_id": paper_id,
                "entities": entities,
                "extraction_model": model,
                "extracted_at": datetime.now(timezone.utc).isoformat(),
            }
            output_file.write(json.dumps(record, ensure_ascii=False) + "\n")
            written += 1
    return written


def cmd_submit(args: argparse.Namespace) -> None:
    client = OpenAI(api_key=_resolve_api_key(args.api_key))

    papers = papers_needing_extraction(args.shards_dir)
    if not papers:
        print("No papers need extraction -- nothing to submit.")
        return
    logger.info("%d paper(s) need extraction", len(papers))

    if len(papers) > args.chunk_size:
        logger.warning(
            "%d papers exceeds --chunk-size %d (OpenAI's enqueued-token cap "
            "means one giant batch gets rejected outright) -- submitting only "
            "the first %d. Use 'run' instead to process everything "
            "automatically in chunks.", len(papers), args.chunk_size, args.chunk_size,
        )
        papers = papers[: args.chunk_size]

    batch = _submit_chunk(client, papers, args.model, args.spacy_model, args.shards_dir, "manual")

    state_path = _state_path(args.shards_dir)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps({
        "batch_id": batch.id,
        "model": args.model,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "request_count": len(papers),
    }))
    logger.info("State saved to %s", state_path)
    print(f"Batch ID: {batch.id}")
    print("Check progress with: uv run python -m src.extraction.batch_api status")


def _load_state(shards_dir: Path) -> dict:
    state_path = _state_path(shards_dir)
    if not state_path.exists():
        raise SystemExit(f"No batch state at {state_path} -- run 'submit' first, or pass --batch-id explicitly.")
    return json.loads(state_path.read_text())


def cmd_status(args: argparse.Namespace) -> None:
    client = OpenAI(api_key=_resolve_api_key(args.api_key))
    batch_id = args.batch_id or _load_state(args.shards_dir)["batch_id"]

    batch = client.batches.retrieve(batch_id)
    counts = batch.request_counts
    print(f"Batch {batch_id}: {batch.status}")
    if counts:
        print(f"  completed={counts.completed}  failed={counts.failed}  total={counts.total}")
    if batch.status == "completed":
        print("Ready to collect: uv run python -m src.extraction.batch_api collect")
    elif batch.status in ("failed", "expired", "cancelled"):
        print(f"Batch did not complete successfully: {batch.status}")
        if batch.errors:
            print(batch.errors)


def cmd_collect(args: argparse.Namespace) -> None:
    client = OpenAI(api_key=_resolve_api_key(args.api_key))
    # Only fall back to saved state for whatever wasn't given explicitly --
    # an explicit --batch-id must work with no state file present at all.
    state = None if args.batch_id else _load_state(args.shards_dir)
    batch_id = args.batch_id or state["batch_id"]
    model = state.get("model", args.model) if state else args.model

    batch = client.batches.retrieve(batch_id)
    if batch.status != "completed":
        print(f"Batch {batch_id} is not completed yet (status={batch.status}). Nothing to collect.")
        return

    if not batch.output_file_id:
        print(f"Batch {batch_id} completed but has no output file (all requests may have failed).")
        return

    content = client.files.content(batch.output_file_id).text
    recovery_path = args.shards_dir / "batch_recovery.extracted.jsonl"
    written = _write_results(content, model, recovery_path)

    logger.info("Wrote %d result(s) to %s", written, recovery_path)
    print(f"Collected {written} result(s) into {recovery_path}")
    print("Next: uv run python -m src.extraction.cli resolve && ... merge")


def cmd_run(args: argparse.Namespace) -> None:
    """Submit -> wait -> collect, chunk after chunk, until every paper
    needing extraction has been attempted. Long-running (each chunk can take
    up to 24h to process, though usually much less) -- run in the
    background. Safe to re-run if interrupted: papers_needing_extraction()
    recomputes fresh each time and naturally skips whatever earlier chunks
    already collected.
    """
    client = OpenAI(api_key=_resolve_api_key(args.api_key))
    chunk_num = 0

    while True:
        papers = papers_needing_extraction(args.shards_dir)
        if not papers:
            logger.info("No papers remain needing extraction -- done.")
            break

        chunk_num += 1
        chunk = papers[: args.chunk_size]
        label = f"{chunk_num:03d}"
        logger.info("Chunk %s: %d paper(s) (%d remaining total)", label, len(chunk), len(papers))

        batch = _submit_chunk(client, chunk, args.model, args.spacy_model, args.shards_dir, label)

        while True:
            time.sleep(args.poll_interval)
            batch = client.batches.retrieve(batch.id)
            counts = batch.request_counts
            logger.info(
                "Chunk %s: batch %s status=%s completed=%s failed=%s",
                label, batch.id, batch.status,
                counts.completed if counts else "?", counts.failed if counts else "?",
            )
            if batch.status in ("completed", "failed", "expired", "cancelled"):
                break

        if batch.status != "completed":
            logger.error("Chunk %s: batch %s ended with status=%s -- stopping.", label, batch.id, batch.status)
            if batch.errors:
                logger.error("%s", batch.errors)
            break

        if not batch.output_file_id:
            logger.warning("Chunk %s: batch %s has no output file (all requests may have failed).", label, batch.id)
            continue

        content = client.files.content(batch.output_file_id).text
        recovery_path = args.shards_dir / f"batch_recovery_{label}.extracted.jsonl"
        written = _write_results(content, args.model, recovery_path)
        logger.info("Chunk %s: wrote %d result(s) to %s", label, written, recovery_path)

    logger.info("All chunks done (%d chunk(s) processed).", chunk_num)
    print("Next: uv run python -m src.extraction.cli resolve && ... merge")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OpenAI Batch API extraction: submit / status / collect.")
    parser.add_argument("--log-level", default="INFO")
    subparsers = parser.add_subparsers(dest="command", required=True)

    submit_parser = subparsers.add_parser(
        "submit", help="Submit ONE chunk (up to --chunk-size papers). Use 'run' to process everything.",
    )
    submit_parser.add_argument("--shards-dir", type=Path, default=DEFAULT_SHARDS_DIR)
    submit_parser.add_argument("--model", default=DEFAULT_MODEL)
    submit_parser.add_argument("--spacy-model", default=DEFAULT_SPACY_MODEL)
    submit_parser.add_argument(
        "--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE,
        help="Max papers in this submission (default: %(default)s, stays under "
        "OpenAI's enqueued-token cap for a single batch).",
    )
    submit_parser.add_argument("--api-key", default=None, help="Defaults to OPENAI_API_KEY in sciagent-KG/.env -- avoid passing this explicitly, it leaks into ps/process listings.")

    status_parser = subparsers.add_parser("status", help="Check a submitted batch job's progress.")
    status_parser.add_argument("--shards-dir", type=Path, default=DEFAULT_SHARDS_DIR)
    status_parser.add_argument("--batch-id", default=None, help="Default: read from the last submit's saved state")
    status_parser.add_argument("--api-key", default=None, help="Defaults to OPENAI_API_KEY in sciagent-KG/.env -- avoid passing this explicitly, it leaks into ps/process listings.")

    collect_parser = subparsers.add_parser("collect", help="Download results from a completed batch job.")
    collect_parser.add_argument("--shards-dir", type=Path, default=DEFAULT_SHARDS_DIR)
    collect_parser.add_argument("--batch-id", default=None, help="Default: read from the last submit's saved state")
    collect_parser.add_argument("--model", default=DEFAULT_MODEL, help="Fallback if not recorded in saved state")
    collect_parser.add_argument("--api-key", default=None, help="Defaults to OPENAI_API_KEY in sciagent-KG/.env -- avoid passing this explicitly, it leaks into ps/process listings.")

    run_parser = subparsers.add_parser(
        "run", help="Submit, wait, and collect chunk after chunk until everything is done. Long-running.",
    )
    run_parser.add_argument("--shards-dir", type=Path, default=DEFAULT_SHARDS_DIR)
    run_parser.add_argument("--model", default=DEFAULT_MODEL)
    run_parser.add_argument("--spacy-model", default=DEFAULT_SPACY_MODEL)
    run_parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    run_parser.add_argument(
        "--poll-interval", type=int, default=DEFAULT_POLL_INTERVAL,
        help="Seconds between status checks while waiting for a chunk (default: %(default)s)",
    )
    run_parser.add_argument("--api-key", default=None, help="Defaults to OPENAI_API_KEY in sciagent-KG/.env -- avoid passing this explicitly, it leaks into ps/process listings.")

    return parser.parse_args()


COMMANDS = {"submit": cmd_submit, "status": cmd_status, "collect": cmd_collect, "run": cmd_run}


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(message)s")
    COMMANDS[args.command](args)


if __name__ == "__main__":
    main()
