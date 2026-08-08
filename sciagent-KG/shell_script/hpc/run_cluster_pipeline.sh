#!/bin/bash
# Cluster-side entry point for domain-KG extraction.
#
# Filters your local copy of the arXiv snapshot down to just the papers
# currently in your Neo4j KG, shards the result, and submits the array job
# (SLURM or LSF) that runs vLLM + spaCy extraction over every shard in
# parallel -- same extraction code (src.extraction.extract) as the local
# Ollama pilot, just pointed at vLLM instead.
#
# Neo4j itself is never touched from the cluster -- only a flat list of
# arxiv_ids crosses the network, not paper text, since the cluster already
# has its own copy of the snapshot.
#
# --- One-time setup, before running this ---
# 1. On your dev machine, export the KG's current paper ids:
#      uv run python -m src.extraction.export --ids-only
#    This writes data/extraction/kg_paper_ids.txt.
# 2. Get the project onto the cluster (git clone/pull) and copy that file
#    there too (scp/rsync) -- it's tiny, just one arxiv_id per line.
# 3. Run shell_script/hpc/setup_cluster_env.sh once on a login node to
#    build .venv/ (gitignored, so it never comes across with git). Every
#    script here uses .venv/bin/python directly, never `uv run`, since
#    compute nodes are commonly air-gapped.
# 4. Edit extract_slurm.sbatch (or extract_lsf.sh) for your cluster's
#    module/conda setup, account/partition/queue, and GPU request syntax.
#
# --- Usage (on the cluster, from a login node) ---
#   shell_script/hpc/run_cluster_pipeline.sh \
#       /path/to/arxiv-metadata-oai-snapshot.json \
#       data/extraction/kg_paper_ids.txt \
#       [shard_size] [concurrency] [scheduler: slurm|lsf]
#
# Examples:
#   shell_script/hpc/run_cluster_pipeline.sh /data/arxiv-snapshot.json data/extraction/kg_paper_ids.txt
#   shell_script/hpc/run_cluster_pipeline.sh /data/arxiv-snapshot.json data/extraction/kg_paper_ids.txt 1000 8 lsf
#
# --- After the array job finishes ---
# rsync data/extraction/shards/*.extracted.jsonl back to your dev machine,
# then run resolve + merge there (they need Neo4j):
#   uv run python -m src.extraction.cli resolve --shards-dir data/extraction/shards --output data/extraction/resolved.jsonl
#   uv run python -m src.extraction.cli merge --resolved-path data/extraction/resolved.jsonl

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
cd "$PROJECT_ROOT"

SNAPSHOT_PATH="${1:?Usage: $0 <snapshot_path> <ids_path> [shard_size] [concurrency] [scheduler: slurm|lsf]}"
IDS_PATH="${2:?Usage: $0 <snapshot_path> <ids_path> [shard_size] [concurrency] [scheduler: slurm|lsf]}"
SHARD_SIZE="${3:-1000}"
CONCURRENCY="${4:-8}"      # max array tasks running at once -- bound by your GPU allocation
SCHEDULER="${5:-slurm}"    # slurm | lsf

SHARDS_DIR="$PROJECT_ROOT/data/extraction/shards"
PYTHON="$PROJECT_ROOT/.venv/bin/python"

if [ ! -x "$PYTHON" ]; then
  echo "No .venv at $PROJECT_ROOT/.venv -- run shell_script/hpc/setup_cluster_env.sh once first." >&2
  exit 1
fi

echo "=== Filtering snapshot for KG papers ==="
"$PYTHON" -m src.extraction.filter_snapshot "$SNAPSHOT_PATH" \
  --ids "$IDS_PATH" \
  --output-dir "$SHARDS_DIR" \
  --shard-size "$SHARD_SIZE"

NUM_SHARDS=$(ls "$SHARDS_DIR"/shard_*.jsonl 2>/dev/null | wc -l | tr -d ' ')
if [ "$NUM_SHARDS" -eq 0 ]; then
  echo "No shards produced -- check that the ids in $IDS_PATH matched the snapshot." >&2
  exit 1
fi

mkdir -p logs

case "$SCHEDULER" in
  slurm)
    echo "=== Submitting SLURM array job: $NUM_SHARDS shard(s), concurrency=$CONCURRENCY ==="
    sbatch \
      --array="0-$((NUM_SHARDS - 1))%${CONCURRENCY}" \
      --export=ALL,PROJECT_DIR="$PROJECT_ROOT",SHARDS_DIR="$SHARDS_DIR" \
      shell_script/hpc/extract_slurm.sbatch
    echo "Submitted. Monitor with: squeue -u \$USER"
    ;;
  lsf)
    echo "=== Submitting LSF array job: $NUM_SHARDS shard(s), concurrency=$CONCURRENCY ==="
    # bsub inherits the submitting shell's environment by default on most
    # sites; if yours doesn't, add an explicit -env option here.
    PROJECT_DIR="$PROJECT_ROOT" SHARDS_DIR="$SHARDS_DIR" \
      bsub -J "kg-extract[1-${NUM_SHARDS}]%${CONCURRENCY}" < shell_script/hpc/extract_lsf.sh
    echo "Submitted. Monitor with: bjobs -u \$USER"
    ;;
  *)
    echo "Unknown scheduler '$SCHEDULER' -- expected 'slurm' or 'lsf'" >&2
    exit 1
    ;;
esac

echo "Once every task completes, rsync $SHARDS_DIR/*.extracted.jsonl back to your dev machine and run resolve + merge there."
