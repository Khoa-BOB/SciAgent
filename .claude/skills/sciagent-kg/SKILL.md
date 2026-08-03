---
name: sciagent-kg
description: Search the SciAgent Neo4j knowledge graph of arXiv papers by vector similarity and expand results via the graph (shared authors, categories, related papers). Use when the user asks to find papers on a topic, discover related/similar work, or get author/category/journal context for a paper already in the graph.
---

# SciAgent Knowledge Graph

## What this is

A Neo4j graph of arXiv paper metadata — `Paper`, `Author`, `Category`, `Journal`, `Version`, `TechnicalReport` nodes (see `sciagent-KG/docs/graph_schema.md` for the full schema) — with a vector index (`paper_embedding_index`) over each paper's title+abstract embedding. Querying is done through `sciagent-KG/src/main.py`, which runs a vector search (`PaperVectorSearch`) and then a graph expansion (`GraphExpander`) for author/category-based related papers.

## When to use

- "Find papers about X"
- "What's related to this paper / arxiv id?"
- "Who else publishes on X" / author or category context for a paper
- Any literature-search or related-work request that should be grounded in this KG rather than general knowledge

## Prerequisites

- `sciagent-KG/.env` has `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD` (`NEO4J_DATABASE` optional, defaults to `neo4j`)
- Neo4j is running (`docker-compose.yaml`) with constraints/indexes applied (`cypher/constrains.cypher`, `cypher/index.cypher`) and papers already loaded + embedded
- Commands run from the `sciagent-KG/` directory — `src` and `queries` are top-level packages, not installed modules

## How to run

```bash
cd sciagent-KG
uv run python -m src.main "<natural language query>" [--top-k N] [--related-limit N] [--no-expand]
```

Example:

```bash
uv run python -m src.main "graph neural networks for molecule generation" --top-k 5
```

- `--top-k` (default 5): number of seed papers from vector search
- `--related-limit` (default 5): number of related papers to surface via graph expansion
- `--no-expand`: skip graph expansion, return only seed papers (faster, no author/category context)

## Output shape

- **Seed papers** (top-k by vector similarity): paper_id, title, score, abstract preview, and — unless `--no-expand` — authors and categories
- **Related papers** (graph expansion only): paper_id, title, and why it's related (shared authors, shared categories, similarity to query)

## Notes / limits

- Embedding model: `google/embeddinggemma-300m` (loaded fresh per run — first call is slow)
- Related-paper candidate pool is fixed at 20 (`DEFAULT_POOL_SIZE` in `graph_expand.py`) before ranking down to `--related-limit`
- Ranking score = `similarity_to_query + 0.1 * shared_authors + 0.05 * shared_categories`
- This only reads the graph — it does not ingest new papers (no ingestion script exists yet)
