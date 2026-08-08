#!/bin/bash
#BSUB -J kg-extract[1-N]%CONCURRENCY   # <-- N = number of shards, CONCURRENCY = max concurrent tasks (LSF arrays are 1-indexed)
#BSUB -n 4
#BSUB -R "rusage[mem=32000]"
#BSUB -gpu "num=1"
#BSUB -W 02:00
#BSUB -o logs/kg-extract-%J-%I.out
#
# LSF (bsub) equivalent of extract_slurm.sbatch -- one shard per array task,
# starts a local vLLM OpenAI-compatible server on this node, runs
# src.extraction.extract against it, then shuts the server down.
#
# LSF array indices are 1-based (LSB_JOBINDEX), mapped here to shard index
# LSB_JOBINDEX - 1 to match shard_0000.jsonl's 0-based naming.
#
# EDIT BEFORE USE -- these are cluster-specific and unknowable without your
# site's docs:
#   - module load / conda activate lines, if vLLM isn't already on PATH
#   - -q (queue), -P (project/account) -- most LSF sites require one or both
#   - -gpu syntax varies a lot by site; check `bsub -gpu` / your site's docs
#   - -R "rusage[mem=...]" units (MB vs GB) are site-config-dependent
#
# Prerequisite: shell_script/hpc/setup_cluster_env.sh has been run once on
# a login node, so .venv/ exists -- this script never calls `uv run` or
# otherwise touches the network, since compute nodes are commonly
# air-gapped.
#
# Normally you won't invoke this directly -- run
# shell_script/hpc/run_cluster_pipeline.sh --scheduler lsf instead, which
# sets the array range, PROJECT_DIR, and SHARDS_DIR for you.

set -euo pipefail

# module load cuda/12.x vllm-env   # <-- adjust to your cluster
# conda activate vllm              # <-- or however vLLM is made available here

PROJECT_DIR="${PROJECT_DIR:-$HOME/SciAgent/sciagent-KG}"
SHARDS_DIR="${SHARDS_DIR:-$PROJECT_DIR/data/extraction/shards}"
MODEL="${MODEL:-Qwen/Qwen2.5-7B-Instruct}"
CONCURRENCY="${CONCURRENCY:-16}"  # papers in flight per task -- vLLM batches these
# server-side; raise/lower based on your GPU's memory and the model size.
PYTHON="$PROJECT_DIR/.venv/bin/python"

SHARD_INDEX=$(( LSB_JOBINDEX - 1 ))
PORT=$(( 8000 + SHARD_INDEX % 1000 ))

# Exclude .extracted.jsonl -- this array's own output files also match
# shard_*.jsonl once other concurrent tasks have produced some, which
# shifts indices and can hand a task an output file as its "input".
mapfile -t SHARD_FILES < <(find "$SHARDS_DIR" -maxdepth 1 -name 'shard_*.jsonl' ! -name '*.extracted.jsonl' | sort)
SHARD_PATH="${SHARD_FILES[$SHARD_INDEX]}"

echo "Task $LSB_JOBINDEX (shard index $SHARD_INDEX): shard=$SHARD_PATH model=$MODEL port=$PORT"

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
"$PYTHON" -m src.extraction.extract "$SHARD_PATH" \
  --base-url "http://127.0.0.1:${PORT}/v1" \
  --model "$MODEL" \
  --concurrency "$CONCURRENCY"

echo "Task $LSB_JOBINDEX done."
