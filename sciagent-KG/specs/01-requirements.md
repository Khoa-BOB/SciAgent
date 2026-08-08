# SciAgent-KG — Requirements

Phase 1 of the SDLC (see [`00-overview.md`](00-overview.md)).

## 1. Who runs this

Unlike `sciagent-backend`, there's no other service calling in — the
"users" of `sciagent-KG` are whoever operates the pipeline directly:

| Role | Needs |
|---|---|
| KG maintainer (scaling the corpus) | Load a new/larger arXiv snapshot without corrupting or duplicating existing data |
| KG maintainer (extending entity coverage) | Run/resume domain-entity extraction against whatever backend (local/HPC/OpenAI) is available and affordable |
| Downstream consumer (`sciagent-backend`, evaluation tooling) | A graph that matches the documented schema exactly, so their queries don't silently break |
| Anyone debugging data quality | A way to check the graph is internally consistent (every paper has a category, no orphaned relationships, etc.) |

## 2. Ingestion — user stories

### Story 1.1 — Load a metadata snapshot

**As a KG maintainer,** I want to load an arXiv metadata JSONL file into
Neo4j, **so that** the graph reflects the corpus I want to work with.

**Acceptance criteria**
- Idempotent: loading the same file twice doesn't create duplicate `Paper`
  nodes (`MERGE` on `arxiv_id`, per `graph_schema.md` §5).
- Resumable: an interrupted load picks up from its checkpoint
  (`src/ingestion/checkpoint.py`) rather than restarting from line 1.
- Papers missing a required field (title, abstract) are still handled
  predictably, not silently dropped without a count.

### Story 1.2 — Embed papers

**As a KG maintainer,** I want every paper embedded into the vector index,
**so that** semantic search has something to query against.

**Acceptance criteria**
- Only embeds papers missing an embedding by default (`only_missing`) —
  re-running after a partial ingest doesn't re-embed the whole corpus.
- `--dry-run` computes without writing, for cost/sanity-checking before a
  large batch.
- Uses the same model (`google/embeddinggemma-300m`) and vector dimension
  (768) as the index configuration in `cypher/index.cypher` — a mismatch
  here breaks every downstream semantic-search query silently, not loudly.

### Story 1.3 — Validate graph integrity

**As anyone depending on this graph,** I want an automated check that the
graph matches its schema invariants, **so that** a bad ingest is caught
before downstream consumers hit it.

**Acceptance criteria**
- Every check in `cypher/validation.cypher` returns a `violations` count;
  `cli.py validate` fails (non-zero exit) if any check reports > 0.
- New invariants can be added as a `-- check: <name>` / `-- description:
  <text>` block without touching `validate.py` itself.

### Story 1.4 — Reproducible sampling

**As a KG maintainer,** I want a deterministic subset of the full corpus,
**so that** I can pilot a pipeline change on a small sample before running
it against the full corpus.

**Acceptance criteria**
- Same `(input_path, n, seed)` always produces the same sample
  (`reservoir_sample`, Algorithm R).
- Works in O(n) memory regardless of input file size (the full snapshot is
  too large to load entirely into memory for sampling purposes).

## 3. Extraction — user stories

See `docs/entity_extraction_pipeline.md` for the full stage-by-stage design;
this section only states the requirements it has to satisfy.

### Story 2.1 — Extend entity coverage without re-running everything

**As a KG maintainer,** I want to add domain entities to newly-ingested
papers without re-processing already-extracted ones, **so that** growing
the corpus incrementally doesn't mean re-paying for extraction on papers
already done.

**Acceptance criteria**
- `papers_needing_extraction()` recomputes fresh from what's on disk —
  no manually-maintained "already done" list to keep in sync.
- Works whether the gap is "never attempted" or "attempted and failed"
  (see extraction pipeline doc's note on `entities: []` being overloaded).

### Story 2.2 — Survive a multi-hour/multi-day run

**As a KG maintainer,** I want a long-running extraction job to be safe to
interrupt and resume, **so that** a laptop sleeping, a terminal closing, or
a rate limit doesn't lose completed work.

**Acceptance criteria**
- Every completed unit of work (a paper, a batch chunk) is durably written
  to disk before the process needs it again.
- Restarting after an interruption doesn't re-submit/re-pay for work
  already completed and collected.

### Story 2.3 — Resolve near-duplicate entities at real corpus scale

**As a KG maintainer,** I want entity resolution to actually finish in
reasonable time, **so that** it's usable on a real (tens-of-thousands of
unique names) corpus, not just a small pilot.

**Acceptance criteria**
- `resolve` completes in minutes, not hours, at current corpus scale
  (~160k unique entity names across all three types) — see
  `03-nfr-testing-deployment.md` §1 for the specific target and the
  performance bug this requirement was written in response to.

### Story 2.4 — Preserve provenance through to Neo4j

**As anyone debugging extraction quality,** I want to see the exact raw
text an entity was extracted from, even after intermediate files are
cleaned up, **so that** "why did this get merged/not merged" is answerable
without re-running extraction.

**Acceptance criteria**
- The pre-resolution name (`raw_name`) is stored as a relationship
  property in Neo4j, not only in an intermediate JSONL file that might not
  exist by the time someone asks the question.

## 4. Explicitly out of scope

- Ingesting full paper text/PDFs (metadata only — see `00-overview.md`).
- Any write path exposed over HTTP (that's explicitly `sciagent-backend`'s
  non-responsibility too — writes stay CLI/batch-job only, see
  `sciagent-backend/specs/02-kg-service-architecture.md` §1).
- Automatic, unattended re-extraction on a schedule — extraction is
  triggered deliberately (cost/rate-limit implications), not on a cron.

## 5. Exit criteria for this phase

- Every story above maps to a concrete stage in `02-architecture.md` and a
  concrete test/check in `03-nfr-testing-deployment.md`.
- No story requires functionality that doesn't already exist in
  `src/ingestion/` or `src/extraction/` — this document describes the
  system as built, refined by what's actually been required of it in
  production (e.g. Story 2.3 and 2.4 both came from real incidents, not
  speculative planning).
