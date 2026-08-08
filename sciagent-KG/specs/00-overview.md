# SciAgent-KG — Specification Index

## Purpose

`sciagent-KG` builds and maintains the knowledge graph that everything else
in the SciAgent product depends on: arXiv paper metadata, embeddings, and
(as of the domain-entity layer) extracted `Method`/`Dataset`/`ResearchTopic`
entities, all stored in Neo4j.

It is a **data pipeline project**, not a service — everything here runs as
CLI commands (`src/ingestion/cli.py`, `src/extraction/cli.py`), one-off
scripts, or scheduled/background batch jobs (HPC array jobs, a long-running
OpenAI Batch API loop). It has no HTTP surface of its own; `sciagent-backend`
is the sibling project that wraps its output as a versioned API (see
`sciagent-backend/specs/00-overview.md`).

```text
sciagent-KG (this project)              sciagent-backend
  ingestion  ──┐                          KG Service
  extraction ──┼──> Neo4j  <──── reads ──── (read-only HTTP API)
  evaluation ──┘
```

## Document map

| Doc | Phase | Content |
|---|---|---|
| [`01-requirements.md`](01-requirements.md) | Discovery | Who runs this, why, user stories + acceptance criteria for both pipelines |
| [`02-architecture.md`](02-architecture.md) | Design | Pipeline stages, stage boundaries, how ingestion and extraction relate |
| [`03-nfr-testing-deployment.md`](03-nfr-testing-deployment.md) | Verification / Deployment | Scale/performance notes, testing, how runs are deployed and monitored |
| [`04-roadmap.md`](04-roadmap.md) | Delivery | Current status, what's shipped, what's next |

This set intentionally does **not** re-derive the graph schema or the
extraction pipeline's internals — those already have their own detailed
reference docs and are linked from here rather than duplicated:

- [`../docs/graph_schema.md`](../docs/graph_schema.md) — full node/relationship/property
  catalog for the metadata graph
- [`../docs/entity_extraction_pipeline.md`](../docs/entity_extraction_pipeline.md) — stage-by-stage
  detail for export → extract → resolve → merge

Treat `docs/` as the "what the data looks like and how it's produced"
reference, and `specs/` as the "why it's built this way, what's required of
it, what's next" project-management layer on top.

## Two pipelines, one graph

### Ingestion (`src/ingestion/`)

Loads raw arXiv metadata (JSONL snapshot) into Neo4j and computes paper
embeddings. Runs first, once per new snapshot/corpus expansion. Stages:
`schema` → `load` → `embed` → `validate`.

### Extraction (`src/extraction/`)

Adds the domain-entity layer on top of an already-ingested graph. Runs
after ingestion, can be re-run independently to extend entity coverage
without touching paper metadata. Stages: `export` → `extract` → `resolve` →
`merge` — see `docs/entity_extraction_pipeline.md` for full detail.

Both pipelines share the same Neo4j connection config (`src/config.py`),
the same checkpoint/resume mechanism (`src/ingestion/checkpoint.py`, reused
by extraction), and the same schema-application entrypoint pattern
(`apply_schema`, idempotent `IF NOT EXISTS` Cypher in `cypher/*.cypher`).

## Non-goals

- **No HTTP/API surface.** That's `sciagent-backend`'s job entirely — this
  project's only consumers are its own CLIs and whatever schedules them
  (a human, a cron job, an HPC array job). This still holds even now that
  `sciagent-backend` has an ingestion write path (`/v1/ingest-jobs`, see
  `sciagent-backend/specs/02-kg-service-architecture.md` §8): that endpoint's
  worker process calls `src/ingestion/`'s existing functions directly, the
  same way the CLI does — it's a new *caller* of this project's code, not a
  new interface added to this project.
- **No agent/LLM-facing retrieval logic beyond what's needed to build the
  graph.** `src/retrieval/` exists here today (semantic search, graph
  expansion) because it was built before `sciagent-backend` existed — see
  `04-roadmap.md` for the plan to have `sciagent-backend`'s KG Service
  consume it in place, rather than duplicating it.
- **No full-paper text ingestion.** Only metadata (title/abstract/authors/
  etc.) — matches the product-level MVP scope in
  `spec/sciagent_webapp_agent_spec.md` §3.2.
