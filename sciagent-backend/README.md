# sciagent-backend

Read-only HTTP API over the SciAgent knowledge graph. Full spec set lives in
[`specs/`](specs/00-overview.md) — start there for the why/what before
changing anything here.

## Layout

```text
sciagent-backend/
├── kg_service/
│   ├── main.py          -- FastAPI app factory, router registration
│   ├── config.py         -- env vars (NEO4J_*, KG_SERVICE_ALLOWED_KEYS)
│   ├── deps.py            -- shared, process-wide Neo4j driver
│   ├── auth.py             -- X-Service-Key allowlist check
│   ├── errors.py            -- structured error model + exception handlers
│   ├── kg_path.py            -- makes sciagent-KG's `queries`/`src` importable
│   ├── routers/               -- one file per resource, thin: parse/validate,
│   │                              call a service, return a schema
│   ├── schemas/                -- Pydantic request/response models
│   └── services/                 -- adapters over sciagent-KG's query/retrieval
│                                     classes -- no Cypher lives here directly
└── tests/
    ├── unit/            -- no Neo4j required
    └── integration/       -- some require a live/fixture Neo4j (see specs/04)
```

Deliberately **not** `src/kg_service/...` — sciagent-KG's own top-level
package is literally named `src`; nesting this project under a same-named
`src/` would make `import src...` ambiguous once both are on `sys.path`
together (see `kg_service/kg_path.py`'s docstring).

## Why this depends on sciagent-KG the way it does

`sciagent-KG` has no build-system config, so it isn't pip-installable as a
library today — it's run in place via `uv run` from within that directory.
Rather than restructure that project's packaging, `kg_service/kg_path.py`
adds `sciagent-KG`'s root to `sys.path` at runtime, so this service can
`import queries...` / `from src.retrieval...` directly. This requires
`sciagent-KG` to be checked out as a **sibling directory** of
`sciagent-backend` (true in this repo today). If that ever stops being true
— separate repos, separate deploy artifacts — revisit by giving `sciagent-KG`
a real `[build-system]` + package config and depending on it as a normal
(editable) `uv` path dependency instead.

## Running locally

```bash
cp .env.example .env   # fill in NEO4J_* (read-only creds) and KG_SERVICE_ALLOWED_KEYS
uv sync
uv run fastapi dev kg_service/main.py
```

`/healthz` and `/readyz` require no auth; every `/v1/...` endpoint requires
`X-Service-Key: <one of KG_SERVICE_ALLOWED_KEYS>`.

## Testing

```bash
uv run pytest tests/unit          # no Neo4j needed
uv run pytest tests/integration   # needs NEO4J_* pointed at a real/test instance
```

## Current status

All `/v1/` endpoints in `specs/03-kg-service-api-spec.md` are implemented
and wired to `sciagent-KG`'s query/retrieval classes: paper lookup, search
(fulltext/semantic/by-author/by-category/by-year), graph expansion,
entities, and stats. The one exception is `GET
/v1/papers/{arxiv_id}/embedding`, which still raises `NotImplementedError`
(surfaced as HTTP `501`) — see `specs/05-kg-service-roadmap.md` Sprint 1.
Sprint 4 hardening (load testing, read-only-credential enforcement test,
OpenAPI contract-diff check in CI, production dashboards/alerting) hasn't
started.

## Docker

Build from the **repository root** (parent of both `sciagent-KG` and
`sciagent-backend`), since the image needs both directories:

```bash
docker build -f sciagent-backend/Dockerfile -t sciagent-kg-service .
```
