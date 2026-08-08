# Domain Entity Extraction Pipeline

## Purpose

Extends the arXiv metadata graph (`graph_schema.md`) with a domain-entity
layer: `Method`, `Dataset`, and `ResearchTopic` nodes pulled out of each
paper's title + abstract by an LLM, connected back to `Paper` via
`USES_METHOD` / `USES_DATASET` / `STUDIES_TOPIC` relationships. This is what
turns the graph from a metadata index into something that can answer "which
papers use X" or "what does this paper use" without full-text guesswork.

Four stages, one CLI (`src/extraction/cli.py`, subcommands `export` /
`extract` / `resolve` / `merge`, plus `schema` and `all`):

```text
Neo4j (Paper.title, Paper.abstract)
        |
        v
   [1] export        -- src/extraction/export.py
        |                shard_NNNN.jsonl (arxiv_id, title, abstract)
        v
   [2] extract        -- src/extraction/candidates.py + llm_client.py + extract.py / batch_api.py
        |                 shard_NNNN.extracted.jsonl / batch_recovery_NNN.extracted.jsonl
        |                 { paper_id, entities: [{name, type}], extraction_model, extracted_at }
        v
   [3] resolve          -- src/extraction/resolve.py
        |                   resolved.jsonl
        |                   { paper_id, entity_type, name, normalized_name, raw_name,
        |                     extraction_model, extracted_at }
        v
   [4] merge              -- src/extraction/merge.py + queries/entities.py
        |
        v
Neo4j (:Method|:Dataset|:ResearchTopic) <-[:USES_METHOD|:USES_DATASET|:STUDIES_TOPIC]- (:Paper)
```

Every stage writes JSONL to disk between steps rather than streaming
end-to-end — extraction is the only stage that costs real money/time (LLM
calls), so its output has to survive independently of whether `resolve`/
`merge` succeed on the first try.

---

## Stage 1 — Export

`src/extraction/export.py`

Pulls `(arxiv_id, title, abstract)` for every paper with both fields
populated, sharded into `shard_NNNN.jsonl` files (default 1,000 papers/shard)
under `data/extraction/shards/`. Nothing in stages 2–4 talks to Neo4j until
stage 4 — extraction runs entirely offline against this flat export, which
matters for HPC runs where the compute nodes can't reach a Neo4j instance
running on a dev machine.

`--ids-only` writes just a flat arxiv_id list instead (`kg_paper_ids.txt`) —
for a cluster that already holds its own copy of the raw arXiv snapshot and
can filter it locally (`src/extraction/filter_snapshot.py`) instead of
shipping paper text over the network.

---

## Stage 2 — Extract

`src/extraction/candidates.py` (spaCy) + `src/extraction/llm_client.py` (LLM
call) + `src/extraction/extract.py` (sync orchestration) or
`src/extraction/batch_api.py` (OpenAI Batch API orchestration).

### 2a. Candidate phrases (spaCy, cheap, runs first)

`extract_candidates()` pulls noun chunks (2–6 content tokens, deduplicated,
capped at 25) out of the abstract with `en_core_web_sm`. This isn't meant to
be correct — it's a shortlist handed to the LLM as a hint ("candidate phrases
from the text... you are not limited to these") so the model has something
concrete to anchor on instead of hunting through raw text blind. Runs on CPU
across the whole corpus before any LLM call.

### 2b. LLM structured extraction

One call per paper (or per small batch, see the note on `--papers-per-request`
below) against an OpenAI-compatible chat-completions endpoint — deliberately
backend-agnostic, since Ollama, vLLM's `--serve` mode, and OpenAI's own API
all expose the same interface. Only `--base-url` / `--model` change between
environments.

**System prompt:**
```text
You extract structured information from scientific paper abstracts.
Given a title and abstract, identify:
- method: named algorithms, models, or techniques the paper uses or proposes
- dataset: named datasets or benchmarks the paper uses or introduces
- topic: the specific research topic(s) the paper studies
Only extract entities explicitly named in the text -- do not infer or
generalize. If none are present for a type, omit them.
Respond with JSON matching the given schema, nothing else.
```

**Response schema** (OpenAI Structured Outputs, `strict: true`):
```json
{
  "entities": [
    {"name": "<exactly as named in the text>", "type": "method | dataset | topic"}
  ]
}
```

`temperature=0`, `max_tokens=512` (`MAX_COMPLETION_TOKENS`) — plenty for
normal abstracts; on an unusually long abstract with a large candidate list
the response can occasionally get cut off mid-JSON and fail to parse (a known,
rare failure mode — see Known Limitations).

### Backends

| Backend | `--base-url` | Use case |
|---|---|---|
| Ollama | `http://localhost:11434/v1` | Local testing, free, slow. Avoid "thinking"/reasoning models (e.g. `qwen3.5`) — they burn the whole completion budget on hidden chain-of-thought and return empty output. Default model: `zephyr:latest`. |
| vLLM | `http://localhost:8000/v1` | HPC, GPU, SLURM/LSF array job — see `shell_script/hpc/`. Raise `--concurrency` a lot; vLLM's throughput comes from batching concurrent requests server-side. |
| OpenAI, synchronous | `https://api.openai.com/v1` | Small jobs only. Hits a hard requests-per-day cap (confirmed 10,000/day on a standard account, rolling 24h window). Requires `--no-thinking-hint`. |
| OpenAI, Batch API | n/a (`src/extraction/batch_api.py run`) | **Recommended for bulk jobs.** Separate quota bucket, 50% cheaper, identical single-paper prompt/schema — no quality tradeoff vs. synchronous. |

**Why not pack multiple papers into one request** (`--papers-per-request`,
`ExtractionClient.extract_batch()`): cuts total request count roughly
proportionally, which fixes a requests/day cap — but measured ~36–44% fewer
entities extracted per paper even at the smallest batch of 2, a real
model-behavior regression, not truncation. The Batch API is almost always
the better fix for a request-count problem, since it has zero quality cost.
`extract_batch()` is kept only for genuinely token-capped (not
request-capped) providers.

### Checkpointing and recovery

`extract.py`'s sync path checkpoints by line index (`src/ingestion/checkpoint.py`)
so a plain resume skips already-processed lines — but a paper that failed
after retries is still checkpointed as "processed" (with `entities: []`), so
a plain resume does **not** retry it.

`batch_api.py:papers_needing_extraction()` is the actual recovery mechanism:
it scans every `*.extracted.jsonl` for records with empty `entities`,
treats them the same as never-attempted, and `batch_api.py run`'s loop
naturally backfills both categories (never-attempted + previously-failed) in
one pass. `run` chunks submissions (default 1,500 papers/chunk — OpenAI's
enqueued-token cap rejects one giant batch outright otherwise) and loops
submit → poll → collect → resubmit until nothing remains.

Note: some papers can never succeed — withdrawn arXiv papers whose
"abstract" is placeholder text (`"This paper has been withdrawn..."`) have
nothing to extract, so `entities: []` for them is correct, not a bug.
`papers_needing_extraction()` doesn't distinguish "genuinely nothing to
extract" from "failed" — a corpus with enough withdrawn papers means `run`'s
loop never naturally reaches zero remaining papers on its own; check whether
remaining "unresolved" papers are legitimately empty before assuming the run
is stuck.

### Output

One record per paper per attempt:
```json
{
  "paper_id": "2212.08674",
  "entities": [
    {"name": "iterative conditional INN (IcINN)", "type": "method"},
    {"name": "toy data", "type": "dataset"}
  ],
  "extraction_model": "gpt-4o-mini",
  "extracted_at": "2026-08-06T09:49:04.257180+00:00"
}
```
`entities: []` is a valid, meaningful outcome (either nothing to extract, or
extraction failed after retries — see above) — not an error state to filter
out before stage 3.

---

## Stage 3 — Resolve

`src/extraction/resolve.py`

Extraction runs **independently per paper** — each LLM call sees one paper
in isolation, with no awareness of how any other paper phrased the same
underlying concept. Across tens of thousands of independent calls, the same
real method/dataset/topic gets written down many different ways ("CNN" /
"CNNs" / "convolutional neural network"). This stage collapses those into
one canonical entity per concept before anything reaches Neo4j.

### Algorithm

Greedy nearest-cluster merge, per entity type (method/dataset/topic
processed independently):

1. Count every unique raw name, most-frequent-first (so the most common
   phrasing claims the canonical slot).
2. Embed every unique name with `google/embeddinggemma-300m` (same model the
   retrieval pipeline uses — no new model dependency).
3. Walk names in frequency order; each one joins the most-similar existing
   cluster if cosine similarity clears `--threshold` (default `0.85`),
   otherwise it starts a new cluster and becomes canonical for that cluster.

Comparisons run as a matrix-vector product (`canonical_embeddings[:k] @
embedding`) against a single preallocated array, not a Python-list `vstack`
rebuilt every iteration — at real corpus scale (tens of thousands of unique
names per type, not the "hundreds to low thousands" the algorithm was
originally sized for) the naive version is effectively O(n²) with a large
constant factor from the repeated array copy, and took 30+ minutes without
finishing; the fixed version processes the full corpus (~160k unique names
across all three types) in about 15 minutes.

### Output

One row per **(paper, mention)** — not per canonical entity — so a paper
with 3 raw entity mentions produces 3 rows even if two of them resolve to
the same canonical entity:

```json
{
  "paper_id": "2605.06736",
  "entity_type": "method",
  "name": "convolutional neural network",
  "normalized_name": "convolutional neural network",
  "raw_name": "convolutional neural network",
  "extraction_model": "gpt-4o-mini",
  "extracted_at": "2026-08-06T09:49:04.257180+00:00"
}
```

`raw_name` is the pre-clustering name exactly as the LLM wrote it for this
specific paper — kept even when it differs from the canonical `name` (i.e. a
merge happened), so that mapping doesn't only exist in memory for the
duration of one `resolve` run. It's carried through to the relationship
itself in stage 4, so it survives in Neo4j independent of whether the
`*.extracted.jsonl` source files are still on disk.

---

## Stage 4 — Merge

`src/extraction/merge.py` + `queries/entities.py`

Idempotent, `MERGE`-based upsert — safe to rerun on failure or after a
partial `resolve` regeneration; a full retry costs some Neo4j round-trips,
nothing more. Per entity type:

1. Upsert one node per unique `normalized_name` (`MERGE (e:Method
   {normalized_name: ...}) ON CREATE SET e.name = ...` — the display `name`
   is set once, at creation, not overwritten on every merge).
2. Upsert one relationship per (paper, canonical entity) pair, with
   properties set (and updated) on every merge.

### Graph shape

| Node label | Key property | Constraint |
|---|---|---|
| `Method` | `normalized_name` | `method_name` (unique) |
| `Dataset` | `normalized_name` | `dataset_name` (unique) |
| `ResearchTopic` | `normalized_name` | `topic_name` (unique) |

| Relationship | Pattern | Properties |
|---|---|---|
| `USES_METHOD` | `(:Paper)-[:USES_METHOD]->(:Method)` | `confidence`, `extraction_model`, `extracted_at`, `raw_name` |
| `USES_DATASET` | `(:Paper)-[:USES_DATASET]->(:Dataset)` | same |
| `STUDIES_TOPIC` | `(:Paper)-[:STUDIES_TOPIC]->(:ResearchTopic)` | same |

Constraints/indexes live in `cypher/constrains.cypher`, applied via
`cli.py schema` (idempotent — every statement is `IF NOT EXISTS`).

`entity_type` never reaches Cypher as free text: `queries/entities.py`'s
`ENTITY_LABELS`/`RELATION_TYPES` are fixed dicts (`method`/`dataset`/`topic`
→ label/relationship name), looked up before the query string is built —
the query is f-string-built but the values going into it are never
caller-supplied, so there's no injection surface despite the string
building.

---

## Running the full pipeline

```bash
cd sciagent-KG
uv run python -m src.extraction.cli schema                                    # once
uv run python -m src.extraction.cli export
uv run python -m src.extraction.batch_api run                                 # or cli.py extract for Ollama/vLLM
uv run python -m src.extraction.cli resolve --output data/extraction/resolved.jsonl
uv run python -m src.extraction.cli merge --resolved-path data/extraction/resolved.jsonl
```

`cli.py all` runs export→extract→resolve→merge in one process — fine for a
local pilot, not for a real corpus (extraction needs to run as a
long-lived/background/HPC job independently of the other stages).

See the `sciagent-kg-extract` and `sciagent-kg-extract-status` Claude Code
skills (`.claude/skills/`) for day-to-day operational commands (starting a
run, checking progress, resuming after a failure).

---

## Known limitations

- **Acronym/expansion pairs don't reliably merge in `resolve`**: e.g. "FORC"
  and "first-order reversal curve" can stay as two separate entities, and
  even same-concept phrasing can split if it doesn't clear the 0.85 cosine
  threshold (observed: "convolutional neural network" and "Convolutional
  Neural Networks" landed as two separate canonical entities in production).
  Not a crash, a precision gap. `raw_name` on the relationship makes this
  discoverable/queryable after the fact even when it doesn't merge.
- **Model choice matters a lot for quality.** Small local models (e.g.
  `zephyr:latest`) frequently mistype entities — physical objects/materials
  as "dataset", descriptive phenomena as "method" — especially outside CS.
  `gpt-4o-mini` measured meaningfully more accurate on the same papers.
- **Rare truncation failures**: an unusually long abstract with a large
  spaCy candidate list can occasionally produce a response that exceeds
  `max_tokens=512` mid-JSON-string, failing to parse and falling back to
  `entities: []` for that paper. Distinguishable from "genuinely nothing to
  extract" only by re-running that specific paper and inspecting the raw
  response.
- **`entities: []` is overloaded**: it means "nothing to extract" (withdrawn
  paper, no concrete technical content) and "extraction failed" both — stage
  2's output alone can't tell these apart; only re-attempting the call can.
