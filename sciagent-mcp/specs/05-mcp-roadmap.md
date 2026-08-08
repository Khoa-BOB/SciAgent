# SciAgent MCP Server — Delivery Roadmap

Phases 3 (implementation) and 6 (operation) of the SDLC (see
[`00-overview.md`](00-overview.md)).

This roadmap is split across two repositories because tool availability is
gated by KG Service completion, not by MCP-layer work — see the dependency
table in §3.

## Sprint A — MCP skeleton + already-live tools

`sciagent-mcp`:
- Repository scaffold: `mcp_service/` FastMCP app, `uv` project.
- `KGServiceClient` (§5 of the architecture doc) with methods for all 11
  endpoints, even though most aren't callable yet.
- Auth (`MCP_ALLOWED_KEYS` inbound, `KG_SERVICE_API_KEY` outbound), error
  mapping including `CAPABILITY_NOT_AVAILABLE` handling (§7 of the
  architecture doc).
- Implement and register `get_paper` and `get_paper_entities` — the first
  is already live in the KG Service (partial fields), the second needs
  KG Service Sprint 3 (§3 below) to actually return data but can be wired
  and tested against the `501` path immediately.
- Non-MCP health route (§6 of the NFR doc), Dockerfile, CI (lint,
  type-check, unit tests).

**Exit**: `get_paper` works end-to-end against a real KG Service instance;
every other tool returns a clean `CAPABILITY_NOT_AVAILABLE` error, verified
by a test.

## Sprint B — KG Service search endpoints (unblocks 5 tools)

`sciagent-backend` + `sciagent-KG` (KG Service's own Sprint 2, see
`sciagent-backend/specs/05-kg-service-roadmap.md`):
- Wire `kg_service/services/search.py`'s six functions to
  `src.retrieval.search.PaperSearch` and
  `src.retrieval.vector_search.PaperVectorSearch` — no new Cypher needed.
- Integration tests against a fixture Neo4j for each search endpoint.

`sciagent-mcp` (parallel, once the above lands in a reachable environment):
- Register `search_papers_semantic`, `search_papers_keyword`,
  `search_papers_by_author`, `search_papers_by_category`,
  `search_papers_by_year`.
- Integration tests against the now-real KG Service search endpoints.

**Exit**: all 5 search tools pass their integration tests end-to-end
through the MCP protocol layer.

## Sprint C — KG Service graph/entities/stats endpoints (unblocks 4 tools)

`sciagent-backend` + `sciagent-KG` (KG Service's own Sprint 3):
- `kg_service/services/graph.py::expand_graph` →
  `src.retrieval.graph_expand.GraphExpander.expand`.
- New read-side Cypher in `sciagent-KG/queries/entities.py`
  (entities-for-paper, papers-for-entity), parameterized by the existing
  `ENTITY_LABELS`/`RELATION_TYPES` fixed dicts.
- `kg_service/services/entities.py` and `kg_service/services/stats.py`
  wired to the new queries.
- Close the `get_paper` field gap (`authors`/`categories`/`journal`/`doi`/
  `update_date`/`versions` currently hardcoded empty — see
  `kg_service/services/papers.py`) with a richer query.

`sciagent-mcp` (parallel):
- Register `expand_paper_neighbors`, `list_entities`,
  `find_papers_by_entity`, `get_kg_stats`.
- Re-test `get_paper` and `get_paper_entities` now that both are fully
  backed — confirm no fields are silently empty anymore.

**Exit**: all 11 tools pass their integration tests end-to-end; the tool
summary in `03-mcp-tool-spec.md` is fully live.

## Sprint D — Hardening and production readiness

- Load testing against the p95 targets in the NFR doc §1.
- Protocol-compliance test wired into CI (schema diff check against
  `03-mcp-tool-spec.md`, mirroring the KG Service's OpenAPI contract test).
- Security review: confirm no Neo4j dependency exists in this codebase,
  confirm both credential allowlists are sourced from a secret manager,
  confirm dependency scan is clean.
- Production deployment, dashboards (tool-call rate, p95/p99 latency by
  tool, error rate by code, KG-Service-unavailable rate), alerting.

**Exit**: matches the exit criteria in
`04-mcp-nfr-testing-deployment.md` §7.

## Dependency table

| MCP tool | Blocked on | KG Service work item |
|---|---|---|
| `get_paper` | — | already live (partial) |
| `get_paper_entities` | Sprint C | new entities-for-paper query |
| `search_papers_semantic` | Sprint B | `PaperVectorSearch` wiring |
| `search_papers_keyword` | Sprint B | `PaperSearch.search_fulltext` wiring |
| `search_papers_by_author` | Sprint B | `PaperSearch.search_by_author` wiring |
| `search_papers_by_category` | Sprint B | `PaperSearch.search_by_category` wiring |
| `search_papers_by_year` | Sprint B | `PaperSearch.search_by_year` wiring |
| `expand_paper_neighbors` | Sprint C | `GraphExpander.expand` wiring |
| `list_entities` | Sprint C | new list-entities query |
| `find_papers_by_entity` | Sprint C | new papers-for-entity query |
| `get_kg_stats` | Sprint C | new stats query |

Sprints B and C are KG Service work (tracked against
`sciagent-backend/specs/05-kg-service-roadmap.md`'s own Sprint 2/3), done in
the `sciagent-backend`/`sciagent-KG` repos; the corresponding MCP-side
registration in each sprint is a same-day follow-on once the endpoint is
reachable in a shared dev/staging environment, not independent multi-week
work — the MCP layer for every tool already exists after Sprint A (§1),
only the KG Service backing is what lands sprint by sprint.

## Definition of Done (per tool)

A tool is done only when:
- It matches its entry in `03-mcp-tool-spec.md` exactly (input schema,
  output shape, error codes).
- It has a unit test (mocked KG client) and an integration test (real KG
  Service) covering the success path and every documented error path.
- It has been called successfully through a real MCP client (Inspector or
  the `mcp` SDK), not just through direct Python function calls.
- Its latency is within the NFR target (§1 of the NFR doc) under the
  load-test profile.

## After this service

Once all 11 tools are live and hardened (Sprint D exit), the next
consumer-side spec to write is the **Agent Orchestrator** — intent
routing, retrieval-strategy selection across these tools (per
`spec/sciagent_webapp_agent_spec.md` §10.2's retrieval-policy table),
evidence fusion, reranking, and citation generation. That spec should be
written against this service's *real* tool latency/error characteristics
(measured in Sprint D), not assumed ones — same principle the KG Service's
own roadmap applied to writing this spec set.
