#!/bin/bash
#SBATCH --job-name=kg-extract
#SBATCH --array=0-N%CONCURRENCY   # <-- set N = number of shards - 1, CONCURRENCY = how many array tasks run at once
#SBATCH --gpus-per-task=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=02:00:00
#SBATCH --output=logs/kg-extract-%A_%a.out
#
# One shard per array task: starts a local vLLM OpenAI-compatible server on
# this node, runs src.extraction.extract against it, then shuts the server
# down. Shards come from `uv run python -m src.extraction.cli export`, run
# once beforehand on the machine hosting Neo4j (compute nodes generally
# can't reach it).
#
# EDIT BEFORE USE -- these are cluster-specific and unknowable without your
# site's docs:
#   - module load / conda activate lines for a vLLM-capable environment
#   - --account / --partition / --qos for your cluster's scheduler
#   - --array upper bound: (number of shards) - 1
#   - PROJECT_DIR, SHARDS_DIR below
#
# Usage: sbatch --array=0-$(( $(ls $SHARDS_DIR/shard_*.jsonl | wc -l) - 1 )) shell_script/hpc/extract_slurm.sbatch

set -euo pipefail

# module load cuda/12.x vllm-env   # <-- adjust to your cluster
# conda activate vllm              # <-- or however vLLM is made available here

PROJECT_DIR="${PROJECT_DIR:-$HOME/SciAgent/sciagent-KG}"
SHARDS_DIR="${SHARDS_DIR:-$PROJECT_DIR/data/extraction/shards}"
MODEL="${MODEL:-Qwen/Qwen2.5-7B-Instruct}"
PORT=$(( 8000 + SLURM_ARRAY_TASK_ID % 1000 ))

SHARD_FILES=("$SHARDS_DIR"/shard_*.jsonl)
SHARD_PATH="${SHARD_FILES[$SLURM_ARRAY_TASK_ID]}"

echo "Task $SLURM_ARRAY_TASK_ID: shard=$SHARD_PATH model=$MODEL port=$PORT"

# Start vLLM's OpenAI-compatible server in the background on this node.
vllm serve "$MODEL" --port "$PORT" --host 127.0.0.1 &
VLLM_PID=$!

cleanup() {
  kill "$VLLM_PID" 2>/dev/null || true
}
trap cleanup EXIT

echo "Waiting for vLLM server to become healthy..."
until curl -sf "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; do
  sleep 5
done

cd "$PROJECT_DIR"
uv run python -m src.extraction.extract "$SHARD_PATH" \
  --base-url "http://127.0.0.1:${PORT}/v1" \
  --model "$MODEL"

echo "Task $SLURM_ARRAY_TASK_ID done."
