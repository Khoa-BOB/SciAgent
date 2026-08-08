# SciAgent MCP Server — Requirements

Phase 1 of the SDLC (see [`00-overview.md`](00-overview.md)).

## Callers

| Caller | Why it calls this service | Auth |
|---|---|---|
| Agent Orchestrator | Retrieves evidence (papers, related work, domain entities) to ground answers, per `spec/sciagent_webapp_agent_spec.md` §10.1 ("Standard Question-Answering Flow") | MCP session credential (see `02-mcp-architecture.md` §6) |
| Evaluation tooling | Calls the same tools directly (not through an LLM) to measure retrieval quality end-to-end through the real agent-facing surface, complementing `sciagent-KG/src/evaluation/`'s lower-level Recall@k/MRR harness | Same MCP session credential |
| A human developer via MCP Inspector | Manual testing/debugging during development | Same MCP session credential |

No other caller is in scope. This service is not called directly by the
BFF or the frontend (`spec/sciagent_webapp_agent_spec.md` §4.2: the MCP
server sits behind the Agent Orchestrator, not exposed to the browser).

## User stories

### Group 1: Paper lookup

#### Story 1.1 — Get a paper by ID

**As the agent orchestrator,**
I want to fetch a specific paper's metadata by its arXiv ID,
so that I can ground an answer in that paper's title, abstract, and
publication details, or render a citation.

**Acceptance criteria**
- Given a valid `arxiv_id`, the tool returns title, abstract, authors,
  categories, journal, DOI, update date, and versions.
- Given an unknown `arxiv_id`, the tool returns a structured "not found"
  result, not a raw HTTP error or an exception.
- The tool never returns the paper's embedding vector (that's internal-only,
  see `00-overview.md`'s position-in-system note).

#### Story 1.2 — Get a paper's extracted entities

**As the agent orchestrator,**
I want to fetch the methods, datasets, and topics extracted for a paper,
so that I can answer questions like "what dataset does this paper use?"
without re-deriving it from the abstract text myself.

**Acceptance criteria**
- Given a valid `arxiv_id`, returns three lists (methods, datasets, topics),
  each possibly empty — an empty list is a valid, non-error outcome (some
  papers have no extracted entities).
- Given an unknown `arxiv_id`, returns a structured "not found" result.

### Group 2: Search

#### Story 2.1 — Semantic search

**As the agent orchestrator,**
I want to search papers by natural-language meaning,
so that I can find conceptually relevant papers when the user's question
doesn't use exact paper terminology (`spec/sciagent_webapp_agent_spec.md`
User Story 2.1).

**Acceptance criteria**
- Given a non-empty query string, returns a ranked list of papers with
  similarity scores.
- Given an empty/whitespace-only query, returns a structured validation
  error, not an empty result set (an empty query and a query with zero
  matches must be distinguishable outcomes).
- Result count never exceeds the documented cap regardless of what the
  caller requests.

#### Story 2.2 — Keyword search

**As the agent orchestrator,**
I want to search papers by exact keyword/full-text match,
so that I can find papers by a specific model, dataset, or technical term
name (`spec/sciagent_webapp_agent_spec.md` User Story 2.2).

**Acceptance criteria**
- Same shape as 2.1, backed by full-text index match instead of vector
  similarity.

#### Story 2.3 — Search by author, category, or year

**As the agent orchestrator,**
I want to filter papers by author name, arXiv category code, or publication
year range,
so that I can answer filtered questions like "what has this author
published since 2022?"

**Acceptance criteria**
- Author search matches by substring on normalized name (matches the KG
  Service's own semantics — no separate fuzzy-matching layer added here).
- Category search requires an exact category code.
- Year search accepts a single year or a range; an invalid range
  (`end_year < start_year`) is a structured validation error.

### Group 3: Graph exploration

#### Story 3.1 — Expand a paper's neighbors

**As the agent orchestrator,**
I want to find papers related to one or more seed papers by shared authors
or categories,
so that I can answer "what else should I read" or "find related work"
questions (`spec/sciagent_webapp_agent_spec.md` User Story 5.3).

**Acceptance criteria**
- Given one or more seed `paper_ids`, returns per-seed context (authors,
  categories, journal) plus a ranked, deduplicated related-paper list.
- Given an empty `paper_ids` list, returns a structured validation error.
- `related_limit` and `pool_size` are capped server-side (by the KG
  Service) regardless of what's requested — this tool passes the caller's
  values through without raising the cap itself.
- An optional `query_embedding` may be supplied to additionally rank by
  similarity to a query; omitting it ranks purely by shared authors/categories.

### Group 4: Domain entities

#### Story 4.1 — Browse known entities

**As the agent orchestrator,**
I want to list or search known methods, datasets, or topics by name,
so that I can resolve a user's loose term ("the CLIP-like approach") to a
canonical entity name before looking up papers that use it.

**Acceptance criteria**
- Given `entity_type` ∈ `{method, dataset, topic}`, returns matching
  entities (optionally filtered by a substring query).
- Given an unrecognized `entity_type`, returns a structured validation
  error listing the valid values.

#### Story 4.2 — Find papers using an entity

**As the agent orchestrator,**
I want to find all papers that use a specific method/dataset or study a
specific topic,
so that I can answer "what papers use X" questions directly from the
domain-entity layer instead of full-text guessing.

**Acceptance criteria**
- Given a valid `entity_type` and `normalized_name`, returns matching
  papers with confidence scores.
- Given an entity that doesn't exist for that type, returns a structured
  "not found" result.

### Group 5: Corpus stats

#### Story 5.1 — Get corpus-level statistics

**As the agent orchestrator (or a developer/evaluator),**
I want aggregate counts (papers, authors, categories, entities by type),
so that I can answer meta-questions about the corpus ("how many papers do
you have on X category") and sanity-check the corpus after an
ingestion/extraction run.

**Acceptance criteria**
- Returns paper count, author count, category count, and entity counts
  broken down by type, plus how many papers have at least one extracted
  entity.

## Explicit exclusions (not building in v1)

- **`compare_papers`** — sketched in `spec/sciagent_webapp_agent_spec.md`
  §4.2 as an example tool, but there's no KG Service endpoint that produces
  a structured comparison; building it would mean inventing new business
  logic and a new KG Service endpoint from scratch rather than wrapping an
  existing, specced one. An agent can already approximate this by calling
  `get_paper` (Story 1.1) twice and reasoning over both results itself —
  revisit as a dedicated tool only if that proves insufficient in practice.
- **`get_citation_context`** — the live Neo4j graph schema
  (`sciagent-KG/docs/graph_schema.md`) has no `CITES` relationship; no
  citation-graph data exists to serve this tool. Out of scope until
  `sciagent-KG`'s ingestion pipeline adds citation extraction.
- **Raw embedding access** (`GET /v1/papers/{arxiv_id}/embedding`,
  `POST /v1/search/semantic/by-embedding`) — these are reranking-internal
  KG Service endpoints, not agent-facing capabilities; exposing raw
  embedding vectors to an LLM tool call has no clear use case and a real
  cost (large payloads). Not wrapped as MCP tools.
