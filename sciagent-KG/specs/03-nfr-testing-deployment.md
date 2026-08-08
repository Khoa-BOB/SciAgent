# SciAgent-KG — Non-Functional Requirements, Testing, Deployment

Phases 2 (design), 4 (verification), and 5 (deployment) of the SDLC (see
[`00-overview.md`](00-overview.md)).

## 1. Scale and performance, as observed in production

Numbers from this project's actual corpus, not projections — useful as a
baseline for judging whether a future change regresses something:

| Metric | Observed value |
|---|---:|
| Corpus size | 36,009 papers |
| Method mentions / unique names | 80,966 / 66,956 |
| Topic mentions / unique names | 94,424 / 73,284 |
| Dataset mentions / unique names | 27,218 / 21,648 |
| `resolve` runtime (fixed algorithm) | ~15.5 minutes for the full corpus |
| `merge` runtime | ~15 seconds for ~203k relationship upserts |
| OpenAI sync requests/day cap hit | 10,000/day (rolling 24h window, not calendar-day) |
| OpenAI Batch API enqueued-token cap | 2,000,000 tokens across in-flight batches |
| Batch API chunk size (tuned to stay under the cap) | 1,500 papers/chunk |

### The `resolve` performance requirement, concretely

`resolve`'s greedy clustering was originally documented as "fine at the
scale of hundreds to low thousands" of unique entity names. Real production
scale is 60–80x that. The original implementation rebuilt a full
`np.vstack` of every canonical embedding on **every single name processed**
— at ~70k unique names with a low merge rate (most names don't share
enough embedding similarity to cluster), this degenerated into an
effectively O(n²) redundant array copy on top of an already O(n²)
comparison cost, and didn't finish in 33+ minutes before being killed.

The fix: write embeddings into one preallocated array and compare via a
sliced matmul (`canonical_embeddings[:k] @ embedding`, BLAS-backed) instead
of reconstructing the array from a Python list every iteration. Same
algorithm, same clustering result, ~15.5 minutes instead of "didn't finish."
**Any future change to `cluster_names()` should be benchmarked against the
full corpus, not a small sample** — the original version looked fine at
pilot scale (hundreds of names) and only broke down at real scale.

## 2. Testing strategy

### Unit tests

- Checkpoint save/load round-trips (`src/ingestion/checkpoint.py`).
- Reservoir sampling determinism: same `(input, n, seed)` → same output,
  across multiple runs.
- Entity clustering: a small fixture set of names with known expected
  merges/non-merges at a given threshold — regression protection for
  `cluster_names()`, independent of the performance concern above.
- `resolve_api_key()`: explicit key wins, missing key raises with a message
  naming the `.env` file to edit, non-OpenAI base URLs don't require a key.

### Data-quality tests (the graph itself)

`cypher/validation.cypher`, run via `cli.py validate` — not unit tests in
the pytest sense, but the equivalent for this project: every check is a
Cypher query returning a `violations` count, and the pipeline fails loudly
(non-zero exit) if any check fails. New invariants (e.g. "every
`USES_METHOD` relationship has a `confidence` between 0 and 1") are added
as new blocks in that file, not new Python.

### Integration tests

- `extract()` against a real (test) Ollama/vLLM endpoint with a known
  paper, asserting the parsed entities match expectations — catches
  prompt/schema drift, not just code bugs.
- `merge_resolved()` against a real (test) Neo4j instance: run it twice
  with the same input, assert the second run doesn't change relationship
  or node counts (idempotency, asserted, not just claimed in a docstring).
- End-to-end pilot: `cli.py all --limit 50` against a disposable Neo4j
  database, asserting the full export→extract→resolve→merge chain
  produces the expected graph shape.

### What's deliberately not tested automatically

- Actual extraction quality (entities/paper, correct type classification)
  — measured manually per model/backend change (e.g. the ~36-44%
  entities-per-paper regression from prompt-batching was found this way),
  not via a fixed pytest assertion, since "correct" here is a judgment call
  against real scientific text, not a deterministic output.
- OpenAI rate-limit behavior — discovered empirically in production (10k/day
  sync cap, 2M-token Batch API cap), not something a test suite can
  practically simulate without hitting the real API.

## 3. Deployment and operation

This project has no deployment target in the service sense — "deployment"
here means "where the pipeline runs":

- **Ingestion**: run locally or on any machine that can reach Neo4j —
  one-shot, not long-running.
- **Extraction, local/Ollama**: local machine, foreground or background
  shell process — for pilots and small jobs.
- **Extraction, HPC**: `shell_script/hpc/` — `setup_cluster_env.sh` once,
  then a SLURM or LSF array job (one shard per task, each running its own
  vLLM server), `rsync`'d results back for `resolve`/`merge` to run locally
  against the machine hosting Neo4j.
- **Extraction, OpenAI Batch API**: `batch_api.py run` as a long-running
  background process (this project's actual production path for the full
  corpus) — safe to kill and restart, `papers_needing_extraction()`
  recomputes what's left on every invocation.

### Monitoring a running extraction job

No dashboard — status is checked via three independent signals (see the
`sciagent-kg-extract-status` Claude Code skill for the exact commands):
1. Local file progress (`*.extracted.jsonl` counts, empty vs. successful).
2. OpenAI's own batch status (`client.batches.list()`) — the ground truth
   for what's actually in flight, since a chunked `run` loop doesn't keep a
   local state file current.
3. Process liveness (`ps aux | grep "batch_api run"`).

All three matter because none alone is sufficient: local files can lag
behind what OpenAI already finished, and OpenAI's batch list doesn't say
whether the local orchestrating loop is still alive to submit the next
chunk.

### Cleanup after a run completes

Once `extract` → `resolve` → `merge` has run to completion:
- `batch_input_*.jsonl` (raw request payloads already sent+collected) —
  safe to delete.
- `.checkpoints/` entries for a fully-completed shard — stale, safe to
  delete.
- Raw `shard_NNNN.jsonl` exports — reproducible from Neo4j via `export` in
  seconds; safe to delete once extraction against them is done.
- `*.extracted.jsonl` / `batch_recovery_*.extracted.jsonl` — **keep.** This
  is the expensive-to-regenerate artifact (real LLM API cost), and the only
  place the pre-resolution `raw_name` provenance exists if `resolved.jsonl`
  ever needs to be regenerated with a different threshold. Deleting these
  is effectively irreversible for whatever data they cover — confirmed the
  hard way when an overly broad glob (`shard_*.jsonl` matching
  `shard_*.extracted.jsonl` too) deleted 14 shards' worth of raw extraction
  output during a cleanup pass. Always exclude `.extracted.jsonl`
  explicitly when scripting deletions here, the same way `cli.py`'s own
  shard-discovery glob already has to (`docs/entity_extraction_pipeline.md`
  notes this exact bug pattern for a different reason).

## 4. Exit criteria for this phase

- Every number in §1 is re-measured (not assumed) after any change to
  `resolve`'s algorithm or the extraction corpus size.
- `cli.py validate` passes with zero violations after every `merge` run
  before that run is considered complete.
- Any script that deletes files under `data/extraction/shards/` explicitly
  excludes `.extracted.jsonl`, verified by inspecting the command before
  running it — not assumed safe because "it looked similar to last time."
