---
name: sciagent-kg-eval
description: Measure SciAgent KG retrieval quality (Recall@k, MRR) against two eval sets — an exhaustive auto-generated self-retrieval set and a curated 20-query paraphrased set. Use when the user asks to benchmark, evaluate, or check retrieval/search quality, or wants to know if a change to search/ranking helped or hurt.
---

# SciAgent KG Retrieval Evaluation

## What this is

A small evaluation harness (`sciagent-KG/src/evaluation/`) that scores `PaperVectorSearch` (the `search` command's vector similarity search, see the `sciagent-kg` skill) against known-answer queries and reports Recall@1/5/10 and MRR. Two eval sets:

- `eval/self_retrieval.jsonl` — every paper's own title paired with its `arxiv_id`, auto-generated from the live graph (`src/evaluation/dataset.py:generate_self_retrieval_queries`). Free and exhaustive (covers the whole corpus), but optimistic — title-matching is an easy proxy, not a real query. Gitignored, regenerate it whenever the corpus changes.
- `eval/paraphrased.jsonl` — 20 hand-written queries paraphrased from real abstracts across 10 categories, deliberately avoiding title vocabulary. This is the meaningful signal: it tests whether semantic search finds a paper when the query shares no words with it, the way a real question would. Committed and static.

## When to use

- "Benchmark/evaluate retrieval quality"
- "Did this change to search or ranking help or hurt?"
- "How good is semantic search on this corpus?"
- Before/after tuning anything in `src/retrieval/` (embedding model, expansion weights, hybrid search, etc.) — get a before/after number instead of eyeballing output

## Prerequisites

- Same as `sciagent-kg`: `sciagent-KG/.env` configured, Neo4j running, schema applied, papers loaded + embedded
- Commands run from the `sciagent-KG/` directory

## How to run

```bash
cd sciagent-KG

# (Re)build the self-retrieval eval set from the current graph
uv run python -m src.evaluation.cli generate

# Score vector search against both eval sets (default) and print Recall@k / MRR
uv run python -m src.evaluation.cli run

# Score a specific file only, with a different result-window size
uv run python -m src.evaluation.cli run --eval-file eval/paraphrased.jsonl --top-k 10
```

## Output shape

A table, one row per `source` plus a `TOTAL` row:

```
Source                   N       MRR       R@1       R@5      R@10
------------------------------------------------------------------
paraphrased             20     0.925    90.00%    95.00%    95.00%
self_retrieval        1249     0.999    99.84%   100.00%   100.00%
------------------------------------------------------------------
TOTAL                 1269     0.998    99.68%    99.92%    99.92%
```

- **MRR**: average of `1/rank` of the expected paper across queries (0 if never found in the fetched results) — rewards ranking the right answer near the top, not just somewhere in the list.
- **Recall@k**: fraction of queries where the expected paper appears anywhere in the top-k results.

## Notes / limits

- Only evaluates `search` (vector similarity via `PaperVectorSearch`) — `by-author`/`by-category`/`by-year`/`fulltext` aren't scored here, since those are exact/structural lookups rather than ranked semantic search.
- Runs one `embed_query()` call per eval query (no batching) — expect the full `self_retrieval` pass to take a couple of minutes at 1,000+ papers.
- Adding more paraphrased queries: append `{"query": ..., "expected_paper_id": ..., "source": "paraphrased"}` lines to `eval/paraphrased.jsonl` (shape defined by `EvalQuery` in `src/evaluation/dataset.py`). Sample real papers first (e.g. via the `sciagent-kg` skill's `by-category`) so queries are grounded in actual abstracts, not invented.
