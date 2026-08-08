#!/bin/bash
# Domain-KG extraction pipeline, local pilot run against Ollama.
#
# Runs export -> spaCy+LLM extract -> resolve -> merge sequentially on a
# small paper sample, using a local Ollama server as the LLM backend (same
# OpenAI-compatible client code that talks to vLLM on HPC -- only
# --base-url/--model differ). Use this to validate the schema and prompt
# quality cheaply before spending HPC GPU time on the full corpus.
#
# Prerequisites: `ollama serve` running, and the model pulled
# (`ollama pull zephyr`). Avoid "thinking"/reasoning models here (e.g.
# qwen3.5) -- they burn their context on chain-of-thought and time out
# instead of emitting structured output.
#
# Usage:
#   shell_script/extract_pipeline_local.sh            # pilot on 200 papers
#   shell_script/extract_pipeline_local.sh 50          # pilot on 50 papers

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

LIMIT="${1:-200}"
SHARDS_DIR="data/extraction/pilot_shards"
RESOLVED_PATH="data/extraction/pilot_resolved.jsonl"
OLLAMA_URL="http://localhost:11434/v1"
MODEL="zephyr:latest"

echo "=== Pilot run: $LIMIT papers, model=$MODEL (Ollama) ==="

echo "--- schema ---"
uv run python -m src.extraction.cli schema

echo "--- export ---"
uv run python -m src.extraction.cli export --output-dir "$SHARDS_DIR" --shard-size "$LIMIT" --limit "$LIMIT"

echo "--- extract ---"
uv run python -m src.extraction.cli extract --shards-dir "$SHARDS_DIR" --base-url "$OLLAMA_URL" --model "$MODEL"

echo "--- resolve ---"
uv run python -m src.extraction.cli resolve --shards-dir "$SHARDS_DIR" --output "$RESOLVED_PATH"

echo "--- merge ---"
uv run python -m src.extraction.cli merge --resolved-path "$RESOLVED_PATH"

echo "=== Pilot run complete. Inspect $RESOLVED_PATH, or query Neo4j for :Method/:Dataset/:ResearchTopic nodes. ==="
