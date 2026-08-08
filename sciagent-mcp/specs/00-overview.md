# SciAgent MCP Server — Specification Index

## Purpose

`sciagent-mcp` exposes the SciAgent knowledge graph to LLM agents as MCP
(Model Context Protocol) tools — paper search, lookup, graph exploration,
and domain-entity browsing — without the agent ever needing to know Cypher,
REST conventions, or which service holds the Neo4j credentials.

This is a *sibling* codebase to `sciagent-KG` and `sciagent-backend`, not a
replacement for either:

- `sciagent-KG` owns ingestion, extraction, and the graph schema — offline,
  batch, write-heavy work.
- `sciagent-backend` (the "KG Service") owns *read* access to that graph
  over versioned HTTP (`/v1/...`) — see
  `sciagent-backend/specs/00-overview.md`.
- `sciagent-mcp` (this spec set) owns translating that HTTP API into MCP
  tools an agent orchestrator can call — it holds **no Cypher, no Neo4j
  driver, and no `sciagent-KG` import**. Its only outbound dependency is the
  KG Service's HTTP API.

The broader product vision (web app, conversational agent, MCP tools,
citations, streaming) is described in `spec/sciagent_webapp_agent_spec.md`.
That spec's §4.2 sketches an illustrative MCP tool list; this spec set is
the concrete, implementable version of that sketch, scoped to what the KG
Service's documented contract (`sciagent-backend/specs/03-kg-service-api-spec.md`)
can actually back.

## Position in the system

```text
Agent Orchestrator
      |
      | MCP Client (Streamable HTTP)
      v
sciagent-mcp  (this service)
      |
      | HTTPS + X-Service-Key
      v
sciagent-backend  ("KG Service")
      |
      | imports as a library
      v
sciagent-KG  (queries/*.py, src/retrieval/*.py)
      |
      v
Neo4j (read-only credentials)
```

`sciagent-mcp` is a thin translation layer: MCP tool call in, KG Service
HTTP call out, KG Service JSON response back translated into MCP tool
content. It never has a network path to Neo4j and never holds Neo4j
credentials of any kind — the KG Service is the sole gatekeeper, matching
`spec/sciagent_webapp_agent_spec.md` §8.3's requirement that "the LLM must
not receive direct unrestricted database access."

## Why build this now, against a partially-stubbed KG Service

`sciagent-backend`'s own roadmap (`sciagent-backend/specs/05-kg-service-roadmap.md`)
says the MCP spec should be written "only after [the KG Service] is actually
implemented." As of this writing, only `/healthz`, `/readyz`, and a partial
`GET /v1/papers/{arxiv_id}` are live; every search, graph-expansion,
entities, and stats endpoint is a stub returning `501 NOT_IMPLEMENTED`.

Decision for this spec set: build the full MCP tool contract now, against
the KG Service's *documented* API spec (not its current implementation
state), and finish the KG Service's stub endpoints as parallel work (see
`05-mcp-roadmap.md`). Rationale:

- The KG Service's REST contract (`03-kg-service-api-spec.md`) is already
  frozen and detailed enough to design against — the risk the original
  roadmap note was guarding against (designing MCP tools around assumed
  rather than real latency/error characteristics) is low here because the
  contract, error model, and NFR targets are already fully specified, not
  assumed.
- Tools map 1:1 to endpoints (see `03-mcp-tool-spec.md`), so each tool can
  go live independently the moment its backing endpoint is implemented —
  there's no MCP-layer rework required when a stub is filled in.
- A `501 NOT_IMPLEMENTED` from the KG Service is treated as a first-class,
  documented tool outcome (see `02-mcp-architecture.md`'s error mapping),
  not a crash — so partially-implemented is a safe, visible state rather
  than a hidden one.

## Document map

| Doc | Phase | Content |
|---|---|---|
| [`01-mcp-requirements.md`](01-mcp-requirements.md) | Discovery | Who calls this, why, per-tool-group user stories + acceptance criteria, explicit exclusions |
| [`02-mcp-architecture.md`](02-mcp-architecture.md) | Design | Service boundary, transport, tech stack, error/auth model |
| [`03-mcp-tool-spec.md`](03-mcp-tool-spec.md) | Design | Concrete tool-by-tool contract (input/output schema, endpoint mapping) |
| [`04-mcp-nfr-testing-deployment.md`](04-mcp-nfr-testing-deployment.md) | Verification / Deployment | Performance targets, test strategy, deployment, security |
| [`05-mcp-roadmap.md`](05-mcp-roadmap.md) | Delivery | Sprint breakdown tied to KG Service completion, tool-unlock dependency table |

## Backend SDLC phases (same shape as `sciagent-backend`'s spec set)

```text
1. Discovery        -- who calls this, what do they need, what's explicitly out of scope
2. Design            -- service boundary, tool contract, error model
3. Implementation     -- build against the contract, not around it
4. Verification       -- unit + integration + protocol-compliance tests
5. Deployment          -- containerize, environment config, CI/CD, health checks
6. Operation            -- monitoring, iteration
```

## Non-goals

- **No write path.** This service never mutates the graph — it doesn't even
  have write endpoints available to call, since the KG Service itself has
  none (`sciagent-backend/specs/00-overview.md` "Non-goals for the KG
  Service specifically").
- **No user identity or authorization.** That belongs to the BFF
  (`spec/sciagent_webapp_agent_spec.md` §4.2: "The MCP server should not
  manage browser sessions, frontend state, or user authentication"). This
  service authenticates the *Agent Orchestrator* as a caller (service-to-service),
  not end users.
- **No LLM calls.** This service does not call a chat/completion model and
  does not construct prompts — it only translates tool calls to HTTP calls
  and HTTP responses back to tool results. (The KG Service embeds *query*
  text server-side for semantic search — see its own non-goals — this
  service doesn't duplicate that either.)
- **No direct Neo4j access, ever.** Enforced architecturally (this codebase
  has no Neo4j driver dependency and no `sciagent-KG` import), not just by
  convention.
- **No composite/derived tools beyond what the KG Service can back today.**
  `compare_papers` and `get_citation_context` from
  `spec/sciagent_webapp_agent_spec.md` §4.2's illustrative list are
  explicitly out of scope for v1 — see `01-mcp-requirements.md` for why.
