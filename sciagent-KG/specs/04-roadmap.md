# SciAgent-KG — Status and Roadmap

Phase 6 of the SDLC (see [`00-overview.md`](00-overview.md)).

## Current status

**Ingestion**: complete for the current corpus. 36,009 papers loaded,
embedded (`google/embeddinggemma-300m`, 768-dim), schema/constraints/indexes
applied. `cli.py validate` is the standing gate for any future load.

**Extraction (domain-entity layer)**: complete for the current corpus.
- 35,981 / 36,009 papers (99.92%) have real extracted entities; the
  remaining 28 are almost entirely withdrawn arXiv papers with no
  extractable content (not a pipeline failure — see
  `docs/entity_extraction_pipeline.md`'s note on `entities: []` being a
  valid outcome).
- Resolved into 53,907 `Method`, 55,749 `ResearchTopic`, 18,421 `Dataset`
  canonical nodes, connected via 202,608 relationships.
- `raw_name` provenance is now stored on every relationship (retroactively
  backfilled via a `resolve` + `merge` re-run), except for the subset of
  papers whose raw `*.extracted.jsonl` source was lost to an over-broad
  cleanup glob before the fix shipped — those relationships exist in the
  graph but lack `raw_name`.

**Evaluation**: a domain-entity benchmark now exists —
`uv run python -m src.evaluation.cli entities`, scoring against a
40-paper hand-labeled sample (`eval/entity_extraction_ground_truth.jsonl`)
and a curated synonym-pair list (`src/evaluation/entity_metrics.py`).
Distinct from `cli.py run`/`expand`, which measure paper retrieval, not
entity quality. Current measured results: extraction 70.2% precision /
72.6% recall overall (dataset precision the weak point at 40.9%);
resolution 0% merge recall on the 3 evaluable known synonym/acronym pairs
(`CNN`/`convolutional neural network`, `RL`/`reinforcement learning`,
`MCTS`/`Monte Carlo Tree Search` all failed to merge).

## Known gaps (not yet addressed)

- **Entity resolution precision**: acronym/expansion pairs and some
  same-concept phrasing don't reliably merge (0.85 cosine threshold misses
  them) — see `docs/entity_extraction_pipeline.md` Known Limitations.
  `raw_name` makes this discoverable per-relationship now, but doesn't fix
  the underlying miss rate. **Now measured, not just anecdotal**: 0% merge
  recall on the 3 evaluable curated synonym pairs (see Evaluation above) —
  embedding similarity alone doesn't reliably catch acronym↔expansion pairs
  even when the expansion is the literal spelled-out acronym (`MCTS` /
  `Monte Carlo Tree Search`).
- **Dataset extraction precision (40.9%, measured)**: the LLM frequently
  extracts generic descriptive phrases as if they were named datasets
  (`"five major AI-powered search systems"`, `"simulated 3D environments"`,
  one case literally extracted the word `"datasets"`) — a systematic prompt
  issue, not random noise. See Evaluation above for the full benchmark.
- **28 permanently-unresolvable papers**: `papers_needing_extraction()`
  can't distinguish "genuinely nothing to extract" (withdrawn paper) from
  "failed, should retry" — a corpus with enough withdrawn papers means a
  `batch_api.py run` loop never naturally reaches zero remaining on its
  own. Worth a small classification step (e.g. flag withdrawn-paper
  placeholder abstracts before extraction, not after) if this pipeline runs
  again against a corpus with more withdrawn papers.
- **`sciagent-backend`'s KG Service can't fully implement `GET
  /v1/papers/{arxiv_id}`** as specced: the existing `PAPER_BY_ID` query only
  returns `paper_id`/`title`/`abstract`/`embedding`, not
  authors/categories/journal/doi/versions. Needs a small additive query in
  `queries/search.py` (or `queries/metadata.py`) — flagged in
  `sciagent-backend/specs/02-kg-service-architecture.md` §8, not yet built.

## Near-term

1. **Add the richer paper-detail query** noted above — small, additive,
   unblocks `sciagent-backend`'s Sprint 1 paper-lookup endpoint fully.
2. **Add read-side entity-lookup Cypher** (papers-for-entity,
   entities-for-paper) to `queries/entities.py`, alongside the existing
   upsert/relate templates — needed for `sciagent-backend`'s Sprint 3
   (entities router).
3. **Add a corpus-stats query** (paper count, entity counts by type) — same
   additive pattern, needed for `sciagent-backend`'s `/v1/stats`.
4. **Add an acronym-detection fallback to `cluster_names()`** (`resolve.py`)
   alongside the embedding-similarity check — e.g. treat a name as a likely
   match if its letters form an acronym of the other name's initials, not
   just cosine similarity ≥ 0.85. Directly targets the measured 0% merge
   recall on acronym/expansion pairs. Zero OpenAI cost (no re-extraction
   needed — reruns against the same `*.extracted.jsonl` files already on
   disk) and directly checkable: rerun `resolve` + `merge`, then
   `cli.py entities` again and confirm merge recall actually moved.
5. **Reject obviously-invalid entity names during `resolve`/`merge`** — the
   literal string `"datasets"`/`"methods"`/`"topics"` and corrupted/garbled
   LaTeX (control characters, mismatched braces) should never become a
   canonical entity. Same zero-cost, immediately-verifiable-via-benchmark
   property as #4.

None of #1–3 change ingestion or extraction — they're net-new, read-only
query additions that `sciagent-backend`'s services layer will call. #4–5
are local, free fixes to the resolution stage, verifiable against the new
benchmark without touching the LLM.

## Medium-term

- **Re-extract the 14 shards' worth of papers** that lost their `raw_name`
  provenance (identifiable via `extracted_at` timestamps predating the
  Batch API switch) — low priority, since the canonical entities and graph
  relationships for those papers are already correct; only the raw-mention
  audit trail is missing.
- **Revisit the resolution threshold/algorithm** if the acronym/expansion
  miss rate turns out to matter for a real downstream use case (e.g. if
  `sciagent-backend`'s search quality is visibly hurt by split entities) —
  superseded in part by Near-term #4 (acronym fallback), but a broader
  threshold retune is still only worth doing against a concrete failure
  case, not blind.
- **Fix the dataset-extraction prompt** (`SYSTEM_PROMPT`/`EXTRACTION_SCHEMA`
  in `llm_client.py`) to reject generic descriptive phrases — e.g. add an
  explicit negative instruction/examples ("do not extract a description of
  the data used, such as 'the dataset used' or a bare count — only extract
  if it has an actual proper name"). Unlike the Near-term fixes, this
  requires spending real OpenAI cost to verify: re-run extraction on a
  sample (not the full corpus) with the revised prompt, re-score with
  `cli.py entities` against the same ground-truth sample, and confirm
  dataset precision (currently 40.9%) actually improves before considering
  a full re-extraction.
- **`src/retrieval/` migration**: decide whether semantic search / graph
  expansion logic stays here (as a library `sciagent-backend` imports, the
  current design — see `sciagent-backend/specs/02-kg-service-architecture.md`
  §1) or moves into `sciagent-backend` outright once that project is the
  only consumer. No urgency while both projects live in the same
  repository with `sciagent-KG` as a sibling-directory import.

## Longer-term / out of scope until requested

- Ingesting a second corpus source (non-arXiv) — would need schema
  extensions beyond `docs/graph_schema.md`'s current arXiv-specific fields
  (`comments`, `report-no`, etc.).
- Automated, scheduled re-extraction as new papers are ingested — currently
  a deliberate, manually-triggered step; see `01-requirements.md` §4.
