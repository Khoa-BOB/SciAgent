---
name: sciagent-kg-ingest
description: Load new arXiv papers (JSONL metadata) into the SciAgent Neo4j knowledge graph — apply schema, batch-load with resumable checkpointing, compute embeddings, and validate the result. Use when the user wants to add more papers to the graph, ingest a new dataset, grow the corpus beyond what's currently loaded, or resume an interrupted load.
---

# SciAgent KG Ingestion

## What this is

A local, resumable ingestion pipeline (`sciagent-KG/src/ingestion/`) that takes arXiv metadata JSONL and turns it into graph data: applies constraints/indexes, batches papers into Neo4j with checkpointed resume, embeds title+abstract for vector search, and runs post-load sanity checks. Orchestrated through one CLI (`sciagent-KG/src/ingestion/cli.py`) with `schema`/`load`/`embed`/`validate`/`all` subcommands.

## When to use

- "Add more papers to the graph"
- "Load this JSONL file into the KG"
- "Grow the corpus" / "I want more than the current N papers"
- "Resume an interrupted load"
- Re-embedding after changing the embedding model

## Prerequisites

- `sciagent-KG/.env` has `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`
- Neo4j is running (`docker-compose.yaml`)
- Commands run from `sciagent-KG/`
- New metadata must be a JSONL file in the raw arXiv snapshot shape (see `sciagent-KG/docs/graph_schema.md` §1.1) — one JSON object per line with `id`, `title`, `abstract`, `authors_parsed`, `categories`, etc.

## Getting more papers to load

If you don't already have a JSONL file to load, sample one from the local corpus (`data/csAI/cs_ai_papers.jsonl`, ~190K papers) without touching the whole thing:

```bash
cd sciagent-KG
uv run python -m src.ingestion.sampling --n 2000 --seed 42 --output ../data/example/sample_2000.jsonl
```

Deterministic (same `--seed`/`--n` always produces the same sample) and O(1) memory (reservoir sampling, single pass) regardless of corpus size.

## How to run

```bash
cd sciagent-KG

# One-shot: schema -> load -> embed -> validate, in sequence
uv run python -m src.ingestion.cli all <path/to/papers.jsonl>

# Or run each stage independently
uv run python -m src.ingestion.cli schema
uv run python -m src.ingestion.cli load <path/to/papers.jsonl> [--batch-size N] [--no-resume] [--reset-checkpoint]
uv run python -m src.ingestion.cli embed [--limit N] [--batch-size N] [--reembed-all] [--dry-run]
uv run python -m src.ingestion.cli validate
```

Example — grow the graph by 2,000 more papers:

```bash
uv run python -m src.ingestion.sampling --n 2000 --seed 43 --output ../data/example/sample_2000_b.jsonl
uv run python -m src.ingestion.cli all ../data/example/sample_2000_b.jsonl
```

## Output shape

- `schema`: logs which constraints/indexes were newly created vs. already existed (idempotent, safe to rerun every time)
- `load`: logs progress per batch (`Loaded N paper(s) so far...`) and the final total
- `embed`: progress bar plus per-batch logs; skips papers that already have an embedding unless `--reembed-all`
- `validate`: a PASS/FAIL table, one row per check (papers without authors/categories, missing title/abstract, duplicate author positions, bad version numbers, papers with >1 submitter); exits non-zero on any FAIL

## Notes / limits

- **Loading is resumable by default**: `load` checkpoints after every successfully committed batch (`.checkpoints/`, gitignored). If interrupted, re-running the exact same command picks up right after the last good batch instead of restarting from line 1 — no flag needed. Use `--reset-checkpoint` to force a full reprocess of that file.
- **Safe to re-run / overlapping samples are fine**: `arxiv_id` (and deterministic author/journal/submitter IDs) are unique-constrained and upserted via `MERGE`, so loading a paper already in the graph just updates it in place rather than duplicating it. Verified in practice: loading a 750-paper sample on top of an existing 500 produced exactly 1,249 Paper nodes, not 1,250.
- **Embedding is the slow step**: `google/embeddinggemma-300m` loads fresh each run; budget real time for a few thousand papers on a local machine.
- After loading more papers, regenerate the `sciagent-kg-eval` skill's self-retrieval eval set so it covers the new papers too: `uv run python -m src.evaluation.cli generate`.
- This only ingests metadata JSONL you already have (or sample via `sampling.py`) — it does not fetch new data from arXiv itself.
