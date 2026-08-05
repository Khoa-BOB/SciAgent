#!/bin/bash
# Embed all Paper nodes that don't yet have an `embedding` property.
#
# Decoupled from `cli.py load` on purpose: loading metadata is cheap, but
# embedding loads a ~300M param SentenceTransformer model and runs inference
# on every paper, which is the slow part. Run this separately, whenever you
# have spare cycles, after `cli.py load` has populated the graph.
#
# Safe to interrupt (Ctrl-C) and rerun: only papers still missing `embedding`
# are processed (see --reembed-all in cli.py to force recomputation).
#
# Usage:
#   shell_script/embed_papers.sh                  # batch size 32
#   shell_script/embed_papers.sh 64                # custom batch size
#   nohup shell_script/embed_papers.sh > /dev/null 2>&1 &   # run in background

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

BATCH_SIZE="${1:-32}"

LOG_DIR="$PROJECT_ROOT/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/embed_$(date +%Y%m%d_%H%M%S).log"

echo "Embedding papers with batch size $BATCH_SIZE"
echo "Logging to $LOG_FILE"

uv run python -m src.ingestion.cli embed --batch-size "$BATCH_SIZE" 2>&1 | tee "$LOG_FILE"
