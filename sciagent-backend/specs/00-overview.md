# SciAgent Backend — Specification Index

## Purpose

`sciagent-backend` is the service layer that exposes the data already built in
`sciagent-KG` (Neo4j knowledge graph: paper metadata + domain entities +
embeddings) as versioned HTTP APIs that other components — the MCP server,
the agent orchestrator, the BFF, evaluation tooling, and any other internal
client — can call without knowing Cypher or touching the database directly.

This is a *sibling* codebase to `sciagent-KG`, not a replacement for it:

- `sciagent-KG` owns ingestion, extraction, and the graph schema — offline,
  batch, write-heavy work (see `sciagent-KG/README.md`,
  `sciagent-KG/docs/graph_schema.md`).
- `sciagent-backend` owns *read* access to that graph over HTTP — online,
  request/response, read-only from the API's point of view. It imports
  `sciagent-KG`'s query builders and retrieval modules (`queries/`,
  `src/retrieval/`) as a library rather than duplicating Cypher.

The broader product vision (web app, conversational agent, MCP tools,
citations, streaming) is described in `spec/sciagent_webapp_agent_spec.md`.
This spec set is the backend-engineering breakdown of that vision, service by
service, starting with the one service everything else depends on: the
**Knowledge Graph (KG) Service**.

## Why the KG service first

Every other backend capability in the product spec — semantic search, hybrid
retrieval, graph exploration, paper detail pages, MCP retrieval tools, agent
evidence retrieval — reads from the same underlying graph. Standing up a
stable, versioned KG API first means:

- The MCP server has a real HTTP contract to wrap instead of embedding Neo4j
  driver calls directly.
- The agent orchestrator and BFF can be built and tested against a mocked or
  real KG service independently of agent/LLM work.
- Retrieval quality (recall@k, MRR — already measured in
  `sciagent-KG/src/evaluation/`) is owned by one service with one set of
  query implementations, instead of being re-implemented per consumer.

## Document map

| Doc | Phase | Content |
|---|---|---|
| [`01-kg-service-requirements.md`](01-kg-service-requirements.md) | Discovery | Who calls this API, why, user stories + acceptance criteria |
| [`02-kg-service-architecture.md`](02-kg-service-architecture.md) | Design | Service boundary, request flow, tech stack, error/versioning model |
| [`03-kg-service-api-spec.md`](03-kg-service-api-spec.md) | Design | Concrete endpoint-by-endpoint REST contract |
| [`04-kg-service-nfr-testing-deployment.md`](04-kg-service-nfr-testing-deployment.md) | Verification / Deployment | Performance targets, test strategy, deployment, security |
| [`05-kg-service-roadmap.md`](05-kg-service-roadmap.md) | Delivery | Sprint breakdown, Definition of Done, what's specced next |

## Backend SDLC phases (applies to every future service, not just KG)

```text
1. Discovery        -- who calls this, what do they need, what's explicitly out of scope
2. Design            -- service boundary, data flow, API contract, error model
3. Implementation     -- build against the contract, not around it
4. Verification       -- unit + integration + contract tests, load test, security review
5. Deployment          -- containerize, environment config, CI/CD, health checks
6. Operation            -- monitoring, on-call, iteration
```

Each future backend service spec (see below) should follow the same
five-phase shape as this one so the specs stay comparable and a new
contributor can find "the API contract" or "the deployment checklist" in the
same relative place every time.

## Planned services (after KG)

Not specced yet — listed here so scope and sequencing is explicit and the KG
service's contract doesn't accidentally paint these into a corner.

| Service | Depends on | Responsibility |
|---|---|---|
| **KG Service** (this spec set) | Neo4j | Read-only HTTP access to papers, search, graph expansion, domain entities |
| Retrieval/MCP Service | KG Service | Wraps KG Service (+ reranking) as MCP tools for the agent |
| Agent Orchestrator | Retrieval/MCP Service | Intent routing, evidence fusion, citation generation, streaming |
| BFF | Agent Orchestrator, App DB | Auth, conversations, collections, SSE, rate limiting (owns the user-facing contract in `spec/sciagent_webapp_agent_spec.md` §6) |
| Ingestion/Extraction control plane (optional) | sciagent-KG | Trigger/monitor ingestion and entity-extraction jobs from an API instead of the CLI, if/when that's needed |

## Non-goals for the KG Service specifically

- **No write endpoints.** Ingestion (`src/ingestion/`) and entity extraction
  (`src/extraction/`) remain offline batch jobs run via the existing CLIs.
  The KG Service never mutates the graph — this keeps its blast radius small
  and its caching story simple (read replicas, no invalidation-on-write
  ordering to reason about).
- **No user identity or authorization.** That belongs to the BFF. The KG
  Service authenticates *callers* (other backend services), not end users.
- **No LLM calls.** Embedding the *query* text for semantic search is the one
  ML-model call this service makes (`sentence-transformers`, already used by
  `src/retrieval/vector_search.py`); it never calls a chat/completion model.
