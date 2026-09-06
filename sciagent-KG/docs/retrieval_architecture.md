# Retrieval Architecture

## Purpose

`src/retrieval/` answers questions against the graph built by ingestion
(`docs/graph_schema.md`) and extraction (`docs/entity_extraction_pipeline.md`):
semantic search over papers and domain entities, graph-based expansion from
a set of known papers, and (new) natural-language querying. As of this
refactor, every retrieval mode that talks to a Neo4j index is implemented on
top of the official [`neo4j-graphrag-python`](https://github.com/neo4j/neo4j-graphrag-python)
package's `Retriever` classes rather than hand-written Cypher — the package
supplies the vector-index query, the fulltext/vector fusion, and the
read-only-Cypher-generation-and-guard logic; this project supplies the
domain schema, the embedding model, and the result shaping.

The one exception is `graph_expand.py`, which stays hand-written Cypher —
see [Why `graph_expand.py` is not a retriever](#why-graph_expandpy-is-not-a-retriever)
for why it doesn't fit the package's abstraction.

This is a refactor, not a new capability: every mode that existed before
(`search`, `by-id`, `by-author`, `by-category`, `by-year`, `fulltext`) still
returns the same shape of result through the same CLI. Two modes are new
(`hybrid`, `nl-query`), and no LLM answer-generation step was added — this
project retrieves; `sciagent-backend` is where an agent turns a retrieval
result into a synthesized answer (see `specs/00-overview.md`'s scope note).

```text
                        src/retrieval/
                              |
        +-----------+--------+--------+-----------+-----------+
        |           |                 |           |           |
   vector_search  entity_search   hybrid_search  graph_expand  nl_query
   .py            .py             .py            .py           .py
        |           |                 |           |           |
   VectorRetriever  VectorRetriever  Hybrid-      hand-written  Text2Cypher
   (Paper)          (Method/Dataset/ Retriever    Cypher        Retriever
                     ResearchTopic,   (Paper,     (SEED_CONTEXT,
                     one per label)   vector +     RELATED_BY_*)
                                      fulltext)
        |           |                 |                          |
        +-----------+--------+--------+--------------------------+
                              |
                     embedder.py (LocalSentenceTransformerEmbedder)
                              |
                     Neo4j (paper_embedding_index, method/dataset/
                            topic_embedding_index, paper_text)
```

---

## The embedder adapter

`src/retrieval/embedder.py`

Every `neo4j_graphrag` retriever that needs a query embedding takes an
object implementing `neo4j_graphrag.embeddings.base.Embedder`
(`embed_query(text) -> list[float]`). `LocalSentenceTransformerEmbedder`
wraps the project's existing `SentenceTransformer("google/embeddinggemma-300m")`
model — the same model ingestion and extraction's `resolve` stage already
use — behind that interface.

This is a project-written adapter, not `neo4j_graphrag`'s own
`[sentence-transformers]` extra: that extra pins
`sentence-transformers>=3.0.0,<4.0.0`, which conflicts with the
`sentence-transformers>=5.6.1` this project needs for `embeddinggemma-300m`
support (confirmed via `uv add` dependency resolution failure before
switching to the adapter). The adapter only needs the base `Embedder`
abstract class, which has no such pin.

---

## Vector search — `vector_search.py`, `entity_search.py`

Both wrap `neo4j_graphrag.retrievers.VectorRetriever`, one instance per
vector index:

| Module | Index(es) | Node label(s) |
|---|---|---|
| `vector_search.py` (`PaperVectorSearch`) | `paper_embedding_index` | `Paper` |
| `entity_search.py` (`EntitySearch`) | `method_embedding_index`, `dataset_embedding_index`, `topic_embedding_index` | `Method`, `Dataset`, `ResearchTopic` |

A Neo4j vector index is defined against a single label, so `EntitySearch`
holds a dict of three `VectorRetriever`s and merges/sorts results by score
across them — same fan-out-and-merge shape the pre-refactor code used, just
with the per-index query delegated to the package.

Each class keeps its pre-refactor public API (`embed_query`, `search`,
`search_by_embedding` returning the same dataclasses) — `main.py` and
`src/evaluation/cli.py` needed zero changes.

**Result shaping**: `VectorRetriever`'s default formatter stringifies the
whole matched node, which isn't useful for downstream code expecting
`paper_id`/`title`/`abstract`/`score`. Both modules pass a custom
`result_formatter` that reads `record["node"]` and `record["score"]`
directly (documented fields on every retriever's raw result record) into a
`RetrieverResultItem.metadata` dict, which the wrapper class then unpacks
into its dataclass.

**Verified, not assumed**: `VectorRetriever` supports two query strategies —
the native `SEARCH ... VECTOR INDEX` Cypher clause, or the older
`db.index.vector.queryNodes` procedure — selected by
`neo4j_graphrag.utils.version_utils.supports_search_clause()`, which checks
for Neo4j `>= 2026.1.0`. Confirmed live against this project's Neo4j
`2026.06.0` instance that it resolves to the SEARCH clause, matching what
the pre-refactor hand-written Cypher already did deliberately (see that
code's own comment on why it moved off the deprecated procedure). This
matters because the package's fallback path would otherwise be a quiet
regression back to deprecated Cypher.

---

## Hybrid search — `hybrid_search.py` (new)

`PaperHybridSearch` wraps `neo4j_graphrag.retrievers.HybridRetriever`,
combining `paper_embedding_index` (vector) and `paper_text` (fulltext,
Lucene) in one call, merged by the retriever's own (naive) ranker. Exposed
as the `hybrid` CLI command.

This has no pre-refactor equivalent — before, vector search (`search`) and
fulltext search (`fulltext`) were two separate, un-merged CLI commands.
Neither alone catches both "semantically close" and "shares exact keywords
with the query" — this mode catches both in one ranked list.

---

## Natural-language querying — `nl_query.py` (new)

`NLGraphQuery` wraps `neo4j_graphrag.retrievers.Text2CypherRetriever`,
exposed as the `nl-query` CLI command. An LLM turns a natural-language
question into Cypher against a fixed schema description
(`NEO4J_SCHEMA` in this module), which the retriever then runs read-only.

**Why the schema is hand-written, not introspected**: the package can
auto-generate a schema string via `neo4j_graphrag.schema.get_schema()`, but
that function requires the APOC procedure `apoc.meta.data` — this project's
`docker-compose.yaml` only enables the `graph-data-science` plugin (for
Leiden community detection, see `src/community/`), not APOC. Rather than add
a new infra dependency for one feature, `NEO4J_SCHEMA` is a static string
mirroring `docs/graph_schema.md` and this pipeline's domain-entity layer —
**keep it in sync by hand** when either changes.

**Backend-agnostic by design**, same pattern as
`src/extraction/llm_client.py`: `build_default_llm()` wraps
`neo4j_graphrag.llm.OpenAILLM` with a configurable `--base-url`/`--model`,
so it runs against local Ollama, vLLM, or OpenAI's API without code changes.
`resolve_api_key()` (imported from `llm_client.py`) is reused so a real API
key still never has to pass through `--api-key` on the command line.

**Safety**: `Text2CypherRetriever` `EXPLAIN`s the LLM-generated Cypher and
inspects `query_type` before ever executing it, refusing anything that
isn't read-only (`Text2CypherRetrievalError` if the check fails) — verified
in `neo4j_graphrag`'s own source, not just documentation. This means a
prompt-injected or hallucinated write/delete statement cannot reach the
graph, independent of how the schema or examples are worded.

**Model-quality dependent, like extraction**: tested against three local
Ollama models on this project's dev machine. A very small model
(`qwen3.5:0.8b`) returned empty/unusable Cypher (fails cleanly with
`Text2CypherRetrievalError`, doesn't hang or corrupt anything); larger local
models (`qwen3.5:latest`, `zephyr:latest`) produced correct Cypher but took
several minutes end-to-end on CPU-only local inference. Same tradeoff
`docs/entity_extraction_pipeline.md`'s "Model choice matters a lot for
quality" note describes for extraction — a hosted or GPU-served model is the
practical choice for real use, local Ollama is for free/offline testing.

---

## Why `graph_expand.py` is not a retriever

`GraphExpander.expand(paper_ids, query_embedding=None, ...)` takes an
**arbitrary, already-known list of paper IDs** (from a prior vector search,
or a single `by-id` lookup) and traverses shared-author/shared-category
relationships from them, re-ranking by a hand-tuned blend of embedding
similarity and relationship-sharing counts (`AUTHOR_WEIGHT`,
`CATEGORY_WEIGHT`).

Every `neo4j_graphrag` retriever that does graph traversal
(`VectorCypherRetriever`, `HybridCypherRetriever`) is triggered by **its own**
fresh vector/hybrid search — the `retrieval_query` Cypher runs against nodes
that specific search just found, not against a caller-supplied ID list. This
doesn't fit `by-id`'s use case at all (the seed paper is already known by
ID, not found via search), and folding it into `search`'s flow only would
have meant two different code paths for the same `expand()` logic depending
on how the seed was obtained. `graph_expand.py` was kept as-is rather than
force a partial, inconsistent fit.

---

## CLI commands (`src/main.py`)

| Command | Retriever / module | Notes |
|---|---|---|
| `search <query>` | `VectorRetriever` (`vector_search.py`) + `graph_expand.py` | Vector search, optionally expanded via shared authors/categories |
| `by-id <arxiv_id>` | `graph_expand.py` | Direct lookup, then expansion from that one known ID |
| `by-author` / `by-category` / `by-year` | `queries/search.py` (unchanged, exact-match Cypher) | No LLM or vector index involved — kept hardcoded deliberately |
| `fulltext <query>` | `queries/search.py`'s `paper_text` fulltext index (unchanged) | Pure keyword match |
| `hybrid <query>` | `HybridRetriever` (`hybrid_search.py`) | New — vector + fulltext fusion |
| `nl-query <question>` | `Text2CypherRetriever` (`nl_query.py`) | New — `--base-url`/`--model`/`--api-key` like `extraction.cli` |

---

## Validation

No dedicated retrieval test suite existed before or after this refactor;
correctness is checked via `src/evaluation/cli.py run` (self-retrieval
MRR/Recall@k against `PaperVectorSearch`) plus manual smoke tests of each
CLI command against the live dev Neo4j instance. Run after any change to
`vector_search.py`/`entity_search.py`:

```bash
uv run python -m src.evaluation.cli generate   # regenerate eval/self_retrieval.jsonl (gitignored)
uv run python -m src.evaluation.cli run --top-k 10
```

Post-refactor result on a 300-query self-retrieval sample: MRR 0.977, R@1
97.3%, R@5/R@10 98.0% — consistent with the pre-refactor hand-written Cypher
(self-retrieval is an optimistic, exhaustive regression signal, not an
absolute quality benchmark — see `generate_self_retrieval_queries`'s
docstring in `src/evaluation/dataset.py`).

---

## Known limitations

- **`entity_search.py` fails at construction, not query time, if an entity
  vector index doesn't exist.** `VectorRetriever.__init__` calls
  `_fetch_index_infos()` eagerly to read the index's dimension/similarity
  function — a dev database that hasn't run the full extraction +
  `index_entities.py` pipeline (only `paper_embedding_index` present, no
  `method`/`dataset`/`topic_embedding_index`) raises immediately on
  `EntitySearch()`, before any query runs. This is a behavior change from
  the pre-refactor code, which only failed once a search against the
  missing index actually ran — functionally equivalent (both fail, neither
  silently returns wrong results), just a different failure point.
- **`nl-query`'s schema string is hand-maintained**, not introspected (see
  above) — a change to `docs/graph_schema.md` or the domain-entity layer
  that isn't mirrored into `NEO4J_SCHEMA` in `nl_query.py` will silently
  degrade Text2Cypher quality (the LLM won't know about the new
  label/property/relationship) rather than error.
- **`nl-query` quality is bounded by the configured LLM**, same as
  extraction — a small/local model can return empty or malformed Cypher
  (surfaces as a clean `Text2CypherRetrievalError`, not a crash or a wrong
  answer) and a capable model can still be slow on CPU-only local inference.
- **No LLM answer-generation step.** `neo4j_graphrag.generation.GraphRAG`
  (retriever + LLM → synthesized answer) was deliberately left out of this
  refactor's scope — every command here returns retrieved graph data, not a
  generated answer. See `specs/00-overview.md`'s scope note on why
  agent/LLM-facing retrieval logic beyond graph-building belongs in
  `sciagent-backend`.
