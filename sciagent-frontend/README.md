# sciagent-frontend

Simple Next.js (App Router) + Tailwind frontend over `sciagent-backend`'s
read-only KG service. Search papers, browse a paper's details and extracted
entities, and check corpus stats.

## Layout

```text
sciagent-frontend/
├── app/
│   ├── page.tsx               -- search (fulltext / semantic)
│   ├── papers/[id]/page.tsx    -- paper detail + entities
│   └── stats/page.tsx           -- corpus stat counts
├── components/                    -- PaperCard, StatCard, ErrorNotice
└── lib/
    ├── api.ts               -- server-only fetch wrapper for kg_service
    └── types.ts               -- response types mirroring the API spec
```

All backend calls happen in Server Components (`lib/api.ts` is marked
`server-only`), so `KG_SERVICE_KEY` never reaches the browser — the
backend's `X-Service-Key` is a service-to-service credential, not a public
one.

## Running locally

You need `sciagent-backend`'s `kg_service` running first (see that
project's README): `uv run fastapi dev kg_service/main.py`, default
`http://localhost:8000`.

```bash
cp .env.example .env.local   # set KG_SERVICE_URL and KG_SERVICE_KEY
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Current status

`sciagent-backend` itself is scaffolding-only right now (per its roadmap) —
only `/healthz`, `/readyz`, and `GET /v1/papers/{id}` are implemented.
Search, entities, graph-expand, and stats return `501 NOT_IMPLEMENTED` until
those sprints land. This frontend is built against the full API spec
(`sciagent-backend/specs/03-kg-service-api-spec.md`) and renders a plain
notice on `501`/unreachable instead of crashing, so pages work end-to-end as
each backend endpoint comes online.
