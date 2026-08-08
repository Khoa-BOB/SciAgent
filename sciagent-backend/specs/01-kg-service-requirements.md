# KG Service — Requirements

Phase 1 of the backend SDLC (see [`00-overview.md`](00-overview.md)).

## 1. What this service is

An HTTP service that answers questions against the SciAgent knowledge graph:
paper metadata (title, abstract, authors, categories, journal, versions),
full-text and semantic search, graph-relationship expansion, and the
extracted domain-entity layer (Method / Dataset / ResearchTopic —
see `sciagent-KG/docs/graph_schema.md` §11 and `sciagent-KG/queries/entities.py`).

It is a **library-backed API wrapper**, not a new query engine: every
endpoint maps to an existing, already-tested query in `sciagent-KG`
(`queries/search.py`, `queries/expansion.py`, `queries/entities.py`,
`src/retrieval/*.py`). Requirements below are about the *contract*, not new
Cypher.

## 2. Callers (this service's users)

Unlike the product-level spec, the KG Service has no human users directly —
its callers are other backend services:

| Caller | Needs |
|---|---|
| Retrieval/MCP Service | Semantic + keyword search, graph expansion, paper lookup — to build MCP tools |
| Agent Orchestrator | Same, plus domain-entity lookups (for method/dataset comparison questions) |
| BFF (paper detail pages, search UI) | Paper lookup, related papers, entity browsing |
| Evaluation tooling (`src/evaluation/`) | Same search/expansion endpoints, called in bulk against an eval dataset |
| Internal ops / debugging | Health, readiness, corpus stats |
| KG maintainer / frontend upload flow | Add new papers to the graph without a terminal — Story 1.8, `02-kg-service-architecture.md` §8 |

## 3. User stories

### Story 1.1 — Look up a paper by ID

**As a caller,** I want a paper's full metadata by its arXiv ID, **so that**
I can render a paper detail page or ground an agent answer in a specific
paper.

**Acceptance criteria**
- Returns title, abstract, authors, categories, journal, DOI, versions where
  present.
- Returns `404` for an unknown ID, not an empty `200`.
- Response time target: see NFR doc (`04-kg-service-nfr-testing-deployment.md`).

### Story 1.2 — Full-text (keyword) search

**As a caller,** I want to search papers by exact terminology, **so that** I
can find papers mentioning a specific model, dataset, or technical term.

**Acceptance criteria**
- Backed by the existing Neo4j full-text index (`paper_text`, see
  `sciagent-KG/docs/graph_schema.md` §8).
- Results are ranked by the index's relevance score; score is returned, not
  hidden.
- An empty query returns `400`, not a full-corpus scan.

### Story 1.3 — Semantic search

**As a caller,** I want to search papers by natural-language meaning rather
than exact keywords, **so that** conceptually relevant papers surface even
without shared vocabulary.

**Acceptance criteria**
- The service embeds the query text server-side (reusing
  `src/retrieval/vector_search.py`'s `google/embeddinggemma-300m` model) —
  callers send text, not vectors, by default.
- An advanced path accepts a pre-computed embedding directly (for callers
  that already embedded the text, e.g. a reranking step that wants to avoid
  a second embed call).
- `top_k` is bounded (see NFR doc) to prevent unbounded result sets.

### Story 1.4 — Structured metadata search

**As a caller,** I want to filter papers by author, category, or year range,
**so that** I can narrow results by known metadata rather than relevance
scoring.

**Acceptance criteria**
- Author search matches on normalized name (reuses `normalize_name`,
  substring match — same semantics as `PAPERS_BY_AUTHOR` today).
- Category search matches an exact category code (e.g. `cs.AI`).
- Year search accepts a start year and optional end year (inclusive range).
- All three are independent endpoints in v1 (not combinable filters) —
  combining filters is out of scope until a caller actually needs it (see
  NFR doc, "Deferred").

### Story 1.5 — Graph expansion / related papers

**As a caller,** I want related papers for a set of seed paper IDs (shared
authors, shared categories, optionally weighted by embedding similarity to a
query), **so that** I can build a broader evidence set or a "related work"
panel.

**Acceptance criteria**
- Accepts 1..N seed paper IDs.
- Returns per-seed context (authors, categories, journal) plus a ranked,
  deduplicated related-paper list — mirrors `GraphExpander.expand()`
  (`src/retrieval/graph_expand.py`) exactly, since that's already the
  validated ranking logic (shared-author/category weighting, optional
  query-embedding similarity).
- Result size is bounded by `related_limit`/`pool_size`, both capped
  server-side regardless of what the caller requests.

### Story 1.6 — Domain entity browsing

**As a caller,** I want to look up papers by extracted Method/Dataset/Topic,
and look up which entities a given paper uses, **so that** I can answer
"which papers use X" or "what methods does this paper use" without writing
Cypher against the new entity layer.

**Acceptance criteria**
- `GET /v1/papers/{id}/entities` returns the paper's Method/Dataset/Topic
  relationships with confidence scores (`USES_METHOD`/`USES_DATASET`/
  `STUDIES_TOPIC`, see `sciagent-KG/queries/entities.py`).
- `GET /v1/entities/{type}/{normalized_name}/papers` returns papers using a
  given entity (reverse direction).
- Entity type is restricted to the three known types (`method`, `dataset`,
  `topic`); an unknown type is a `400`, not a silently-empty result.

### Story 1.7 — Corpus and health visibility

**As an operator,** I want liveness/readiness checks and basic corpus stats,
**so that** I can verify the service and its Neo4j connection are healthy,
and sanity-check corpus size after an ingestion/extraction run.

**Acceptance criteria**
- `/healthz` never touches Neo4j (process-liveness only).
- `/readyz` executes a trivial Neo4j query and fails closed if the driver
  can't reach the database.
- `/v1/stats` returns paper count, entity counts by type, and last-updated
  timestamp if available — read-only, no auth beyond service-to-service.

### Story 1.8 — Add new papers without the CLI

**As a KG maintainer (or a frontend upload flow acting on their behalf),** I
want to upload a metadata file and have it ingested into the graph, **so
that** growing the corpus doesn't require terminal access to `sciagent-KG`.

**Acceptance criteria**
- `POST /v1/ingest-jobs` accepts a JSONL upload, validates it synchronously
  (so a malformed file fails in the same request, not silently later), and
  returns a job ID immediately — ingestion itself runs asynchronously.
- `GET /v1/ingest-jobs/{job_id}` reports status and, on success, counts
  (papers loaded, embedded, validation violations).
- Reuses `sciagent-KG`'s existing idempotent `load_metadata`/`run_embedding`
  functions exactly — re-uploading a file with papers already in the graph
  doesn't create duplicates (same `MERGE`-on-`arxiv_id` guarantee as Story
  1.1 in `sciagent-KG/specs/01-requirements.md`).
- Gated by a separate, write-scoped credential/key from every read endpoint
  above — see `02-kg-service-architecture.md` §8.
- Does **not** trigger entity extraction — that stays a deliberate, separate
  step (§8.4 of the architecture doc).

## 4. Explicitly out of scope for v1

- Any write/mutate endpoint beyond `/v1/ingest-jobs` (Story 1.8) — entity
  extraction in particular stays CLI-driven; see architecture doc §8.4.
- Pagination cursors beyond simple `limit`/`offset` (deferred until a caller
  needs to page through more than one bounded result page).
- Combined multi-filter search (author + category + year in one call).
- Per-end-user authentication/authorization (BFF's responsibility).
- Rate limiting per end user (BFF's responsibility) — this service still
  needs basic abuse protection against its direct (internal) callers; see
  NFR doc.
- GraphQL — REST/JSON matches the rest of the codebase's tooling and keeps
  the contract simple to version.

## 5. Exit criteria for this phase

- Every story above has a corresponding endpoint in
  [`03-kg-service-api-spec.md`](03-kg-service-api-spec.md).
- Every acceptance criterion maps to a testable assertion in
  [`04-kg-service-nfr-testing-deployment.md`](04-kg-service-nfr-testing-deployment.md) §Testing.
- No story requires a Cypher query that doesn't already exist in
  `sciagent-KG/queries/` or `sciagent-KG/src/retrieval/` — if one does, it's
  flagged as a new query to add during implementation, not assumed away.
