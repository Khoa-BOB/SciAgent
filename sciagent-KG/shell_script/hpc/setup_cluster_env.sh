#!/bin/bash
# One-time cluster setup: build the project's Python environment locally on
# the cluster.
#
# .venv/ is gitignored, so it never comes across with git clone/pull --
# every other script under shell_script/hpc/ calls .venv/bin/python
# directly (never `uv run`), because compute nodes are commonly air-gapped
# and can't do uv's dependency resolution/download over the network. This
# script is the one place that needs network access -- run it once on a
# login node before submitting any array jobs.
#
# Prerequisites: `uv` available on the login node (module load uv, pip
# install --user uv, or curl -LsSf https://astral.sh/uv/install.sh | sh).
#
# Usage: shell_script/hpc/setup_cluster_env.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
cd "$PROJECT_ROOT"

echo "=== Syncing Python environment from uv.lock ==="
uv sync --frozen

echo "=== Downloading spaCy candidate-extraction model ==="
.venv/bin/python -m spacy download en_core_web_sm

echo "=== Done. .venv/ is ready at $PROJECT_ROOT/.venv -- cluster jobs use .venv/bin/python directly, no uv or network access needed on compute nodes. ==="
