# SciAgent-KG — Architecture

Phase 2 of the SDLC (see [`00-overview.md`](00-overview.md)). This is the
stage-boundary/design-decision layer; see `docs/graph_schema.md` and
`docs/entity_extraction_pipeline.md` for the data-level detail this
document deliberately doesn't repeat.

## 1. Overall shape

```text
Raw arXiv JSONL snapshot
        |
        v
  INGESTION  (src/ingestion/)
  schema -> load -> embed -> validate
        |
        v
     Neo4j  <───────────────┐
        |                    |
        v                    |
  EXTRACTION  (src/extraction/)
  export -> extract -> resolve -> merge
```

Ingestion and extraction are **sequential, not interleaved**: extraction's
`export` stage reads `Paper.title`/`Paper.abstract` that ingestion already
wrote, and extraction's `merge` stage is the only point where it writes
back to Neo4j. There's no scenario where both pipelines write to the graph
concurrently in normal operation.

## 2. Why file-based hand-offs between stages

Every stage boundary is a JSONL file on disk, not a function call or a
message queue. This is deliberate:

- **Extraction is expensive and slow** (LLM calls, sometimes hours/days).
  If `resolve` or `merge` has a bug, re-running them costs nothing but
  compute — because `extract`'s output already survived to disk
  independently. Losing that property (e.g. by streaming extract → resolve
  in one process) would mean a bug in `resolve` risks re-paying for
  extraction to recover.
- **HPC runs can't reach Neo4j directly.** `export` produces a flat file
  specifically so `extract` can run on a compute node with no path to the
  Neo4j instance (see `docs/entity_extraction_pipeline.md` Stage 1).
- **Every stage is independently resumable/re-runnable** as a consequence
  — `resolve` can be re-run with a different `--threshold` without
  touching `extract`'s output at all, which is exactly what happened when
  `raw_name` provenance was added retroactively (regenerate `resolved.jsonl`,
  re-run the idempotent `merge`, done).

The cost of this choice is disk usage and a manual "did I run the next
stage" step — judged acceptable for a pipeline that's operated
deliberately, not on a schedule.

## 3. Checkpointing and idempotency, as a system-wide pattern

Three different consistency strategies are used, matched to what each stage
actually needs:

| Stage | Strategy | Why |
|---|---|---|
| `ingestion load` | Line-index checkpoint (`src/ingestion/checkpoint.py`) | Sequential file read — resuming by line index is exact and cheap |
| `extraction extract` (sync) | Same checkpoint module, reused | Same shape of problem (sequential shard read) |
| `extraction extract` (Batch API) | Recomputed-fresh set difference (`papers_needing_extraction()`) | Work isn't sequential — chunks complete out of order, and failures need retrying, not skipping; a line-index checkpoint can't express "retry paper 4 but not paper 5" |
| `extraction merge` | Neo4j `MERGE` (idempotent by construction) | Writing to Neo4j is cheap and safe to repeat; no checkpoint file needed at all, "just rerun it" is a valid recovery strategy |

Picking the cheapest-sufficient strategy per stage, rather than one
checkpoint mechanism everywhere, is why `merge` doesn't need its own state
file (see `merge_resolved`'s docstring) while `extract` does.

## 4. Backend-agnostic extraction, concretely

`src/extraction/llm_client.py`'s `ExtractionClient` targets the OpenAI
chat-completions wire format specifically because three different real
backends (Ollama, vLLM, OpenAI) all speak it — one client, one prompt, one
schema, parameterized only by `--base-url`/`--model`/`--api-key`. The
alternative (a backend-specific client per provider) was never built;
adding a fourth OpenAI-compatible backend requires no code change, only a
different `--base-url`.

The OpenAI Batch API is the one exception with its own code path
(`batch_api.py`) — it isn't a chat-completions call at all (it's a
Files-API-plus-polling workflow), so it can't share `ExtractionClient`. It
does share the exact same prompt/schema construction (`build_batch_requests`
calls the same `EXTRACTION_SCHEMA`/`SYSTEM_PROMPT` semantics as the sync
path), which is what keeps its output quality identical to the synchronous
path — see `docs/entity_extraction_pipeline.md`'s note on why
`--papers-per-request` batching (a *prompt-level* batching approach) was
rejected in favor of this (a *transport-level* batching approach): packing
multiple papers into one prompt measurably hurt extraction quality, while
the Batch API changes nothing about what's asked per paper, only how the
request is transported and rate-limited.

## 5. Security boundary

- Neo4j credentials in `src/config.py` are read from `.env`
  (`python-dotenv`), never hardcoded, never passed as a CLI argument.
- `OPENAI_API_KEY` follows the same pattern (`resolve_api_key()` in both
  `llm_client.py` and `batch_api.py`) — explicitly **not** accepted as a
  bare CLI flag value in normal operation, because a secret passed via
  `--api-key` is visible in `ps`/process listings to any local user. This
  was a real vulnerability found and fixed during this project's
  development, not a hypothetical.
- This project's Neo4j credentials are read-write (it's the only thing
  that legitimately writes to the graph). `sciagent-backend`'s KG Service
  connects with a *separate*, read-only credential set — see
  `sciagent-backend/specs/04-kg-service-nfr-testing-deployment.md` §3. Never
  reuse this project's write credentials for a service that should only
  ever read.

## 6. Exit criteria for this phase

- Every stage boundary in `docs/entity_extraction_pipeline.md`'s pipeline
  diagram has a documented consistency/resumability strategy here.
- The read/write credential boundary between `sciagent-KG` and
  `sciagent-backend` is unambiguous and enforced at the Neo4j user level,
  not just by convention.
