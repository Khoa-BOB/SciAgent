---
name: sciagent-kg
description: Search the SciAgent Neo4j knowledge graph of arXiv papers by vector similarity, arxiv_id, author, category, submission year, or fulltext keyword, and expand results via the graph (shared authors, categories, related papers). Use when the user asks to find papers on a topic, look up a known paper, discover related/similar work, browse an author/category/year, or get author/category/journal context for a paper already in the graph.
---

# SciAgent Knowledge Graph

## What this is

A Neo4j graph of arXiv paper metadata — `Paper`, `Author`, `Category`, `Journal`, `Version`, `TechnicalReport` nodes (see `sciagent-KG/docs/graph_schema.md` for the full schema) — with a vector index (`paper_embedding_index`) over each paper's title+abstract embedding and a fulltext index (`paper_text`) over title+abstract. Querying is done through `sciagent-KG/src/main.py`, a subcommand CLI: `search` (vector similarity, via `PaperVectorSearch`) and `by-id` both run a graph expansion afterward (`GraphExpander`, shared-author/category related papers); `by-author`, `by-category`, `by-year`, and `fulltext` (via `PaperSearch`) are standalone lookups.

## When to use

- "Find papers about X" → `search`
- "What's related to this paper / arxiv id?" → `by-id`
- "What has author X published?" → `by-author`
- "Show me what's in category X" → `by-category`
- "What was published in year X (or between X and Y)?" → `by-year`
- "Find papers mentioning the exact phrase X" → `fulltext`
- Any literature-search or related-work request that should be grounded in this KG rather than general knowledge

## Prerequisites

- `sciagent-KG/.env` has `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD` (`NEO4J_DATABASE` optional, defaults to `neo4j`)
- Neo4j is running (`docker-compose.yaml`) with constraints/indexes applied (`sciagent-KG/src/ingestion/schema.py`, or by hand via `cypher/constrains.cypher`/`cypher/index.cypher`) and papers already loaded + embedded (`sciagent-KG/src/ingestion/cli.py`)
- Commands run from the `sciagent-KG/` directory — `src` and `queries` are top-level packages, not installed modules

## How to run

```bash
cd sciagent-KG

# Semantic search (vector similarity) + graph expansion
uv run python -m src.main search "<natural language query>" [--top-k N] [--related-limit N] [--no-expand]

# Look up a known paper by arxiv_id + graph expansion from it
uv run python -m src.main by-id <arxiv_id> [--related-limit N] [--no-expand]

# Find papers by author name (partial match, e.g. "Grabec" matches "I. Grabec")
uv run python -m src.main by-author "<name>" [--limit N]

# List papers in a category
uv run python -m src.main by-category <category_code> [--limit N]

# List papers first submitted in a year, or a year range
uv run python -m src.main by-year <year> [--to <end_year>] [--limit N]

# Exact-keyword search over title/abstract (fulltext index, not embeddings)
uv run python -m src.main fulltext "<keywords>" [--limit N]
```

Examples:

```bash
uv run python -m src.main search "graph neural networks for molecule generation" --top-k 5
uv run python -m src.main by-id 0903.0174
uv run python -m src.main by-author "Grabec"
uv run python -m src.main by-category cs.CL --limit 5
uv run python -m src.main by-year 2024 --to 2025 --limit 5
uv run python -m src.main fulltext "syntactic parsing" --limit 5
```

- `--top-k` (default 5, `search` only): number of seed papers from vector search
- `--related-limit` (default 5, `search`/`by-id` only): number of related papers to surface via graph expansion
- `--no-expand` (`search`/`by-id` only): skip graph expansion, return only the seed paper(s) (faster, no author/category context)
- `--limit` (default 10, `by-author`/`by-category`/`by-year`/`fulltext`): max papers to return
- `--to` (`by-year` only): end year (inclusive) for a range; omit for a single year

## Output shape

- **`search`/`by-id` seed papers**: paper_id, title, abstract preview, and — unless `--no-expand` — authors and categories. `search` also shows a similarity score per seed paper.
- **`search`/`by-id` related papers** (graph expansion, unless `--no-expand`): paper_id, title, and why it's related (shared authors, shared categories, similarity to the seed)
- **`by-author`/`by-category`/`by-year`/`fulltext`**: paper_id, title, abstract preview, plus the matched author name (`by-author`), submission year (`by-year`), or fulltext relevance score (`fulltext`)
- **`by-id` on an unknown arxiv_id**: a plain "No paper found" message, not an error

## Notes / limits

- Embedding model: `google/embeddinggemma-300m` (loaded fresh per run — first call is slow). Only `search` and the expansion step of `by-id` need it; `by-author`/`by-category`/`by-year`/`fulltext` don't load the model at all.
- Related-paper candidate pool is fixed at 20 (`DEFAULT_POOL_SIZE` in `graph_expand.py`) before ranking down to `--related-limit`
- Ranking score = `similarity_to_query + 0.1 * shared_authors + 0.05 * shared_categories`
- `by-author` matches on a normalized substring of `Author.normalized_name` (accent/punctuation/case-insensitive), not an exact match
- `by-year` filters on `Paper.first_submitted_at` (the paper's original submission date), not `update_date` (last metadata revision, which can be years later) — this is deliberate, see `docs/graph_schema.md`
- This only reads the graph — to ingest new papers, see `sciagent-KG/src/ingestion/cli.py` (`schema`/`load`/`embed`/`validate`/`all` subcommands)
