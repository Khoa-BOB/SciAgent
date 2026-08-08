# SciAgent MCP Server — Tool Specification

Phase 2 of the SDLC (see [`00-overview.md`](00-overview.md)). This is the
concrete tool contract; see
[`02-mcp-architecture.md`](02-mcp-architecture.md) for conventions (error
model, list-response shape, auth) that apply to every tool below without
being repeated per-tool.

Every tool maps to exactly one endpoint in
`sciagent-backend/specs/03-kg-service-api-spec.md` — that doc is the
authoritative source for exact response fields; this doc adds the MCP-facing
tool name, description (what the LLM sees), and input schema.

---

## 1. `get_paper`

Wraps `GET /v1/papers/{arxiv_id}`.

**Description (shown to the LLM):** "Get full metadata for a single paper
by its arXiv ID — title, abstract, authors, categories, journal, DOI,
update date, and version history."

**Input schema**
```json
{"arxiv_id": {"type": "string", "description": "arXiv identifier, e.g. '2401.12345' or '0704.0001'"}}
```
Required: `arxiv_id`.

**Output**
```json
{
  "paper_id": "0704.0001",
  "title": "...",
  "abstract": "...",
  "authors": ["..."],
  "categories": ["hep-ph"],
  "journal": "Phys.Rev.D76:013009,2007",
  "doi": "10.1103/PhysRevD.76.013009",
  "update_date": "2008-11-26",
  "versions": ["v1", "v2"]
}
```

**Errors**: `PAPER_NOT_FOUND`.

---

## 2. `get_paper_entities`

Wraps `GET /v1/papers/{arxiv_id}/entities`.

**Description:** "Get the methods, datasets, and research topics extracted
for a paper, with confidence scores. Returns empty lists if the paper has
no extracted entities — that is a valid outcome, not an error."

**Input schema**
```json
{"arxiv_id": {"type": "string"}}
```
Required: `arxiv_id`.

**Output**
```json
{
  "paper_id": "2401.12345",
  "methods": [{"name": "Graph Attention Network", "confidence": 0.9}],
  "datasets": [{"name": "ogbn-arxiv", "confidence": 0.85}],
  "topics": [{"name": "molecular property prediction", "confidence": 0.8}]
}
```

**Errors**: `PAPER_NOT_FOUND`.

---

## 3. `search_papers_semantic`

Wraps `GET /v1/search/semantic`.

**Description:** "Search papers by natural-language meaning (semantic/vector
similarity). Use for broad conceptual questions where the user doesn't name
an exact technique — e.g. 'papers about using transformers for protein
folding'."

**Input schema**
```json
{
  "query": {"type": "string", "description": "Natural-language search query"},
  "top_k": {"type": "integer", "description": "Max results", "default": 5, "maximum": 50}
}
```
Required: `query`.

**Output**
```json
{"items": [{"paper_id": "2401.12345", "title": "...", "abstract": "...", "score": 0.812}], "count": 1}
```

**Errors**: `EMPTY_QUERY` (if `query` is blank).

---

## 4. `search_papers_keyword`

Wraps `GET /v1/search/fulltext`.

**Description:** "Search papers by exact keyword or phrase match against
title and abstract (full-text index). Use when the user names a specific
model, dataset, gene, or technical term verbatim."

**Input schema**
```json
{
  "query": {"type": "string"},
  "limit": {"type": "integer", "default": 10, "maximum": 100}
}
```
Required: `query`.

**Output**
```json
{"items": [{"paper_id": "2401.12345", "title": "...", "abstract": "...", "score": 4.82}], "count": 1}
```

**Errors**: `EMPTY_QUERY`.

---

## 5. `search_papers_by_author`

Wraps `GET /v1/search/by-author`.

**Description:** "Find papers by a given author name (substring match,
case/accent-insensitive)."

**Input schema**
```json
{
  "author_name": {"type": "string"},
  "limit": {"type": "integer", "default": 10, "maximum": 100}
}
```
Required: `author_name`.

**Output**: same list shape as §3/§4, each item additionally includes
`matched_by` (the matched author's display name).

**Errors**: none beyond generic validation (empty `author_name` is a valid,
zero-result query, not an error — unlike search queries, an author-name
filter has no meaningful distinction between "empty filter" and "filter
matched nothing").

---

## 6. `search_papers_by_category`

Wraps `GET /v1/search/by-category`.

**Description:** "Find papers in a given arXiv category (exact code, e.g.
'cs.AI', 'hep-ph')."

**Input schema**
```json
{
  "category_code": {"type": "string"},
  "limit": {"type": "integer", "default": 10, "maximum": 100}
}
```
Required: `category_code`.

**Output**: same list shape as §3.

**Errors**: `CATEGORY_NOT_FOUND`.

---

## 7. `search_papers_by_year`

Wraps `GET /v1/search/by-year`.

**Description:** "Find papers first submitted within a year or year range
(inclusive)."

**Input schema**
```json
{
  "start_year": {"type": "integer"},
  "end_year": {"type": "integer", "description": "Defaults to start_year if omitted"},
  "limit": {"type": "integer", "default": 10, "maximum": 100}
}
```
Required: `start_year`.

**Output**: same list shape as §3.

**Errors**: `INVALID_YEAR_RANGE` (if `end_year < start_year`).

---

## 8. `expand_paper_neighbors`

Wraps `POST /v1/graph/expand`.

**Description:** "Given one or more seed papers, find related papers via
shared authors or shared categories, ranked by relevance. Optionally weight
ranking by similarity to a query. Use for 'find related work' or 'what else
should I read' questions."

**Input schema**
```json
{
  "paper_ids": {"type": "array", "items": {"type": "string"}, "description": "One or more seed arXiv IDs"},
  "query_embedding": {"type": "array", "items": {"type": "number"}, "description": "Optional — omit to rank purely by shared authors/categories"},
  "related_limit": {"type": "integer", "default": 5, "maximum": 50},
  "pool_size": {"type": "integer", "default": 20, "maximum": 200}
}
```
Required: `paper_ids` (non-empty array).

**Output**
```json
{
  "seed_context": {
    "2401.12345": {"authors": ["Jane Doe"], "categories": ["cs.AI"], "journal": null}
  },
  "related_papers": [
    {"paper_id": "2312.00001", "title": "...", "shared_authors": ["Jane Doe"], "shared_categories": [], "similarity_to_query": 0.0}
  ]
}
```

**Errors**: `EMPTY_PAPER_IDS`.

**Note**: this tool does not accept raw embeddings from an LLM in practice
— `query_embedding` exists in the schema because the KG Service accepts it,
but no MCP tool in this spec produces an embedding for an agent to pass
through (see `01-mcp-requirements.md` exclusions: raw-embedding tools are
not exposed). Agents should normally omit `query_embedding` and rely on
shared-author/category ranking.

---

## 9. `list_entities`

Wraps `GET /v1/entities/{entity_type}`.

**Description:** "Browse or search known methods, datasets, or research
topics by name. Use to resolve a loose term (e.g. 'the CLIP-like approach')
to a canonical entity name before calling find_papers_by_entity."

**Input schema**
```json
{
  "entity_type": {"type": "string", "enum": ["method", "dataset", "topic"]},
  "query": {"type": "string", "description": "Optional substring filter; omit to list all"},
  "limit": {"type": "integer", "default": 20, "maximum": 200}
}
```
Required: `entity_type`.

**Output**
```json
{"items": [{"name": "Graph Attention Network", "normalized_name": "graph attention network"}], "count": 1}
```

**Errors**: `UNKNOWN_ENTITY_TYPE` (message lists the three valid values).

---

## 10. `find_papers_by_entity`

Wraps `GET /v1/entities/{entity_type}/{normalized_name}/papers`.

**Description:** "Find papers that use a given method/dataset or study a
given topic. Use list_entities first if you don't already have the exact
normalized entity name."

**Input schema**
```json
{
  "entity_type": {"type": "string", "enum": ["method", "dataset", "topic"]},
  "normalized_name": {"type": "string", "description": "Exact normalized entity name, from list_entities"},
  "limit": {"type": "integer", "default": 20, "maximum": 200}
}
```
Required: `entity_type`, `normalized_name`.

**Output**
```json
{"items": [{"paper_id": "2401.12345", "title": "...", "confidence": 0.9}], "count": 1}
```

**Errors**: `UNKNOWN_ENTITY_TYPE`, `ENTITY_NOT_FOUND`.

---

## 11. `get_kg_stats`

Wraps `GET /v1/stats`.

**Description:** "Get corpus-level statistics: total papers, authors,
categories, and domain-entity counts by type. Use for meta-questions about
the corpus, not for answering research questions."

**Input schema**: none (no parameters).

**Output**
```json
{
  "paper_count": 36009,
  "author_count": 128441,
  "category_count": 176,
  "entity_counts": {"method": 4213, "dataset": 1876, "topic": 5502},
  "papers_with_entities": 35981
}
```

**Errors**: none beyond the generic `KG_SERVICE_UNAVAILABLE` path.

---

## Tool summary

```text
get_paper                  -> GET  /v1/papers/{arxiv_id}
get_paper_entities          -> GET  /v1/papers/{arxiv_id}/entities
search_papers_semantic        -> GET  /v1/search/semantic
search_papers_keyword          -> GET  /v1/search/fulltext
search_papers_by_author          -> GET  /v1/search/by-author
search_papers_by_category         -> GET  /v1/search/by-category
search_papers_by_year              -> GET  /v1/search/by-year
expand_paper_neighbors               -> POST /v1/graph/expand
list_entities                         -> GET  /v1/entities/{entity_type}
find_papers_by_entity                  -> GET  /v1/entities/{entity_type}/{normalized_name}/papers
get_kg_stats                            -> GET  /v1/stats
```

Every tool here maps to exactly one KG Service endpoint (§8 of
`sciagent-backend/specs/03-kg-service-api-spec.md`'s endpoint summary,
minus the two internal-only embedding endpoints — see
`01-mcp-requirements.md` exclusions).
