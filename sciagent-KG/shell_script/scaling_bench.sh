#!/bin/bash
# Build a performance/quality scaling curve across corpus sizes.
#
# Runs entirely on a throwaway Neo4j instance (docker-compose.bench.yaml:
# separate container, ports, and volumes) so the live 21k-paper graph and
# its in-flight embed job are never touched. Only one Neo4j instance runs
# at a time -- the bench container is torn down (including its volume)
# after each size, so memory/disk never accumulates across sizes.
#
# For each size N: samples N papers (reusing an existing sample file if
# already generated), loads + embeds them into a fresh bench DB, then runs
# the eval CLI (--record) and perf.py against it. Results land in the same
# eval/results.jsonl and bench/results.jsonl used for the main corpus, each
# record tagged with its corpus_size so you can compare across sizes.
#
# This re-embeds every paper at every size from scratch (no reuse across
# sizes), so it's slow -- expect this to take a while at the larger sizes.
# Run it in the background:
#   nohup shell_script/scaling_bench.sh > /dev/null 2>&1 &
#
# Usage:
#   shell_script/scaling_bench.sh                  # sizes: 1000 5000 10000 20000
#   shell_script/scaling_bench.sh 2000 8000        # custom sizes

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

if [ "$#" -eq 0 ]; then
  SIZES=(1000 5000 10000 20000)
else
  SIZES=("$@")
fi

COMPOSE_FILE="docker-compose.bench.yaml"
BENCH_USER="neo4j"
BENCH_PASSWORD="myStrongPassword123"

export NEO4J_URI="bolt://localhost:7688"
export NEO4J_USERNAME="$BENCH_USER"
export NEO4J_PASSWORD="$BENCH_PASSWORD"
export NEO4J_DATABASE="neo4j"

LOG_DIR="$PROJECT_ROOT/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/scaling_bench_$(date +%Y%m%d_%H%M%S).log"
echo "Logging to $LOG_FILE"

{
  for N in "${SIZES[@]}"; do
    echo "=== Corpus size: $N ==="

    docker compose -f "$COMPOSE_FILE" up -d

    echo "Waiting for bench Neo4j to accept connections..."
    until docker exec neo4j-bench cypher-shell -u "$BENCH_USER" -p "$BENCH_PASSWORD" "RETURN 1" >/dev/null 2>&1; do
      sleep 2
    done

    SAMPLE_FILE="data/example/sample_${N}.jsonl"
    if [ ! -f "$SAMPLE_FILE" ]; then
      uv run python -m src.ingestion.sampling --n "$N" --output "$SAMPLE_FILE"
    fi

    uv run python -m src.ingestion.cli schema
    uv run python -m src.ingestion.cli load "$SAMPLE_FILE" --reset-checkpoint
    uv run python -m src.ingestion.cli embed
    uv run python -m src.ingestion.cli validate

    uv run python -m src.evaluation.cli generate
    uv run python -m src.evaluation.cli run --record
    uv run python -m src.evaluation.perf

    echo "Tearing down bench instance for size $N"
    docker compose -f "$COMPOSE_FILE" down -v
  done

  echo "Scaling curve complete. See eval/results.jsonl and bench/results.jsonl."
} 2>&1 | tee "$LOG_FILE"
