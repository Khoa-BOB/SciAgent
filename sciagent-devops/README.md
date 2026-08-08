# sciagent-devops — Deployment & Pipeline Runbook

Step-by-step instructions for standing up SciAgent end to end: build the
knowledge graph in Neo4j, then serve it through the KG Service API.

## 0. What's actually deployable today

| Component | Status | What it is |
|---|---|---|
| `sciagent-KG` | Working pipelines, no HTTP surface | CLI-driven ingestion (arXiv metadata → Neo4j) + extraction (Method/Dataset/Topic entities) |
| `sciagent-backend` | Scaffolding | FastAPI read-only API over the graph. Only `/healthz`, `/readyz`, `GET /v1/papers/{arxiv_id}` are implemented — everything else in `specs/03-kg-service-api-spec.md` returns `501` for now (see `sciagent-backend/README.md` "Current status") |
| `sciagent-frontend` | Empty | Not started |
| `sciagent-mcp` | Empty | Not started |

So "the whole pipeline" today means: **Neo4j → sciagent-KG ingestion →
sciagent-KG extraction → sciagent-backend KG Service**. This doc covers all
four steps plus how to verify each one.

Source of truth for anything below that changes: `sciagent-KG/specs/`,
`sciagent-KG/docs/`, `sciagent-backend/specs/`.

---

## 1. Prerequisites

- Docker + Docker Compose
- [`uv`](https://docs.astral.sh/uv/) (Python package/venv manager — both
  projects are `uv`-based, Python ≥3.12)
- An LLM backend for the entity-extraction stage — pick one:
  - **OpenAI API key** (recommended for a real run — Batch API is 50%
    cheaper and is the path this project actually uses in production), or
  - **Ollama** installed locally (`ollama pull zephyr`) for a free local
    pilot/test run
- Optional: a raw arXiv metadata snapshot if you want to load your own
  corpus instead of the sample files already under `data/example/`
  (the "arXiv Dataset" Kaggle snapshot — same JSON shape documented in
  `sciagent-KG/docs/graph_schema.md` §1.1)

All commands below assume the repo root as `$REPO_ROOT` (parent of
`sciagent-KG`, `sciagent-backend`, `sciagent-devops`).

---

## 2. One-time environment setup

```bash
cd $REPO_ROOT/sciagent-KG
uv sync
uv run python -m spacy download en_core_web_sm   # needed by the extraction stage's candidate-phrase step

cd $REPO_ROOT/sciagent-backend
uv sync
```

Create `sciagent-KG/.env` (no `.env.example` ships for this one — these are
the vars `src/config.py` / `src/extraction/llm_client.py` read):

```bash
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=<the password you set in step 3>
NEO4J_DATABASE=neo4j

OPENAI_API_KEY=<only needed for the OpenAI extraction backend>
HF_TOKEN=<only needed if a HuggingFace model you use is gated>
```

Create `sciagent-backend/.env` from its template:

```bash
cd $REPO_ROOT/sciagent-backend
cp .env.example .env
```

then fill in:

```bash
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j                 # see the read-only-credentials note in §6
NEO4J_PASSWORD=<same password>
NEO4J_DATABASE=neo4j

KG_SERVICE_ALLOWED_KEYS=<comma-separated list of caller API keys you invent, e.g. dev-key-1>
```

`sciagent-devops/.env.example` in this folder mirrors the same values for
the Docker Compose stack in §5 — copy it to `.env` there too.

---

## 3. Start Neo4j

Use the compose file in this folder (it's the one the rest of this doc
assumes; `sciagent-KG/docker-compose.yaml` is an equivalent standalone copy
used by that project's own scripts — don't run both at once, they claim the
same ports).

```bash
cd $REPO_ROOT/sciagent-devops
cp .env.example .env      # set NEO4J_PASSWORD, KG_SERVICE_ALLOWED_KEYS here
docker compose up -d neo4j
```

Wait for it to accept connections, then confirm:

```bash
docker exec -it $(docker compose ps -q neo4j) \
  cypher-shell -u neo4j -p "$NEO4J_PASSWORD" "RETURN 1"
```

Browser UI: http://localhost:7474 (bolt on `7687`).

---

## 4. Run the ingestion pipeline (arXiv metadata → graph)

From `sciagent-KG`, against the Neo4j you just started:

```bash
cd $REPO_ROOT/sciagent-KG

# 1. Apply constraints/indexes (idempotent, safe to rerun)
uv run python -m src.ingestion.cli schema

# 2. Load metadata. Defaults to data/example/mock_500.jsonl (500-paper
#    sample) if you pass no path — good for a first smoke test.
uv run python -m src.ingestion.cli load data/example/sample_20000.jsonl

# 3. Compute paper embeddings (the slow step — ~300M-param model,
#    inference per paper). Safe to Ctrl-C and rerun: only un-embedded
#    papers are processed.
uv run python -m src.ingestion.cli embed

# 4. Sanity-check the loaded graph
uv run python -m src.ingestion.cli validate
```

Or run all four as one step (fine for a pilot, not for a large corpus —
`embed` is long-running):

```bash
uv run python -m src.ingestion.cli all data/example/sample_20000.jsonl
```

To load your own corpus, put a JSONL file in the same shape as
`data/arxiv/arxiv-metadata-oai-snapshot.json` (one arXiv record per line)
anywhere and pass its path to `load`. `src/ingestion/sampling.py` can
reservoir-sample a smaller subset first if you don't want the full
snapshot.

`embed_papers.sh` wraps step 3 with logging, useful for a long background
run:

```bash
nohup shell_script/embed_papers.sh > /dev/null 2>&1 &
```

**Checkpoint:** at this point Neo4j has `Paper` nodes with metadata and
vector embeddings, but no `Method`/`Dataset`/`ResearchTopic` layer yet.

---

## 5. Run the extraction pipeline (domain entities → graph)

Four stages: `export → extract → resolve → merge`. Full detail in
`sciagent-KG/docs/entity_extraction_pipeline.md` — this is the condensed
version.

```bash
cd $REPO_ROOT/sciagent-KG

uv run python -m src.extraction.cli schema     # once — constraints for Method/Dataset/ResearchTopic
uv run python -m src.extraction.cli export     # Paper.title/abstract -> data/extraction/shards/shard_NNNN.jsonl
```

Then run `extract` against whichever backend you have available:

```bash
# Local pilot (free, needs `ollama serve` + `ollama pull zephyr` first) --
# avoid "thinking" models like qwen3.5, they burn the token budget on
# hidden reasoning and return empty output.
uv run python -m src.extraction.cli extract --base-url http://localhost:11434/v1 --model zephyr:latest

# OR: OpenAI Batch API -- recommended for a real corpus, 50% cheaper than
# sync, no quality tradeoff. Long-running; safe to kill and restart, it
# recomputes what's left every time it's invoked.
uv run python -m src.extraction.batch_api run
```

`shell_script/extract_pipeline_local.sh [N]` runs export→extract→resolve→merge
against Ollama on an N-paper pilot in one shot — use this first to sanity-check
prompt/schema quality before spending real time/money on the full corpus.

Finish the pipeline:

```bash
uv run python -m src.extraction.cli resolve --output data/extraction/resolved.jsonl
uv run python -m src.extraction.cli merge --resolved-path data/extraction/resolved.jsonl
uv run python -m src.ingestion.cli validate   # cypher/validation.cypher covers both the metadata and entity layers
```

Or all four stages in one process (pilots only — `cli.py all` under
`src/extraction`, not `src/ingestion`):

```bash
uv run python -m src.extraction.cli all --limit 200
```

If you're driving this from Claude Code rather than a terminal, the
`sciagent-kg-extract` and `sciagent-kg-extract-status` skills in
`.claude/skills/` wrap the same commands with day-to-day operational
guidance (resuming after a failure, checking batch job progress).

**Checkpoint:** Neo4j now has `(:Paper)-[:USES_METHOD|USES_DATASET|STUDIES_TOPIC]->(:Method|:Dataset|:ResearchTopic)`.

---

## 6. Deploy the KG Service (read API)

The backend image needs `sciagent-KG` as a sibling directory inside the
build context (`kg_service/kg_path.py` resolves it at `../sciagent-KG`), so
it must be built from the **repo root**, not from inside `sciagent-backend`.

### Option A — Docker Compose (this folder)

```bash
cd $REPO_ROOT/sciagent-devops
docker compose up -d --build kg-service
```

This builds `sciagent-backend/Dockerfile` with `$REPO_ROOT` as context and
connects it to the `neo4j` service already running from §3 over the compose
network (`bolt://neo4j:7687`).

### Option B — Plain Docker

```bash
cd $REPO_ROOT
docker build -f sciagent-backend/Dockerfile -t sciagent-kg-service .
docker run -d --name kg-service -p 8000:8000 --env-file sciagent-backend/.env \
  -e NEO4J_URI=bolt://host.docker.internal:7687 \
  sciagent-kg-service
```

### Option C — Local dev (no Docker for this part)

```bash
cd $REPO_ROOT/sciagent-backend
uv run fastapi dev kg_service/main.py
```

### Verify

```bash
curl http://localhost:8000/healthz   # no auth
curl http://localhost:8000/readyz    # no auth, fails 503 if Neo4j is unreachable

curl -H "X-Service-Key: <one of KG_SERVICE_ALLOWED_KEYS>" \
  http://localhost:8000/v1/papers/0704.0001
```

A `501` from any other `/v1/...` route is expected right now — see §0.

---

## 7. Read-only credentials — the honest caveat

`sciagent-backend/specs/04-kg-service-nfr-testing-deployment.md` §3
requires the KG Service to connect with a Neo4j user that has **no write
privileges**, enforced at the database level, separate from the
write-capable credentials `sciagent-KG`'s ingestion/extraction CLIs use.

Role-based access control (`CREATE ROLE`, `GRANT`/`DENY`) requires **Neo4j
Enterprise Edition or Aura** — the `neo4j:latest` Community image in this
repo's compose files can't create a second, genuinely-read-only user. For
local dev, both `sciagent-KG` and `sciagent-backend` sharing the single
`neo4j` account (as in §2 above) is an accepted shortcut, not the target
end state.

When you move to a real deployment (Aura, or self-hosted Enterprise),
provision it properly:

```cypher
CREATE ROLE kg_reader;
GRANT ACCESS ON DATABASE neo4j TO kg_reader;
GRANT MATCH {*} ON GRAPH neo4j TO kg_reader;
DENY WRITE ON GRAPH neo4j TO kg_reader;

CREATE USER kg_service_readonly SET PASSWORD '<generate one>' CHANGE NOT REQUIRED;
GRANT ROLE kg_reader TO kg_service_readonly;
```

Then point `sciagent-backend/.env`'s `NEO4J_USERNAME`/`NEO4J_PASSWORD` at
`kg_service_readonly`, keeping the ingestion/extraction `.env` on the
original write-capable account.

---

## 8. Optional: evaluation / benchmarking

Retrieval-quality (Recall@k, MRR) and scaling benchmarks live in
`sciagent-KG/src/evaluation/` and `shell_script/scaling_bench.sh`
(runs entirely against the throwaway `docker-compose.bench.yaml` stack, not
the live graph). If driving from Claude Code, the `sciagent-kg-eval` skill
wraps this. Not required to have a working deployment — useful once you're
tuning retrieval quality.

---

## 9. Day-2 operations quick reference

| Task | Command |
|---|---|
| Re-run ingestion on a bigger snapshot | `cli.py load <path>` (resumable via checkpoint; `--reset-checkpoint` to force a full reprocess) |
| Extend entity coverage after loading more papers | Re-run `export → extract → resolve → merge`; `merge` is idempotent (`MERGE`-based upsert), safe to rerun |
| Check a running extraction job | `sciagent-kg-extract-status` skill, or manually: local `*.extracted.jsonl` counts, `client.batches.list()` for OpenAI Batch jobs, `ps aux \| grep "batch_api run"` for process liveness |
| Validate graph integrity | `uv run python -m src.ingestion.cli validate` — runs `cypher/validation.cypher`, which covers both the metadata and entity layers |
| Roll back a bad deploy of the KG Service | Redeploy the previous image tag — the service is stateless, no migration to roll back |
| Clean up after a completed extraction run | See `sciagent-KG/specs/03-nfr-testing-deployment.md` §3 "Cleanup after a run completes" — **never** delete `*.extracted.jsonl`, only the raw shards/batch inputs |

---

## 10. Toward a real CI/CD pipeline

Not implemented yet — `spec/sciagent_webapp_agent_spec.md` §13 Phase 5 and
`sciagent-backend/specs/04-kg-service-nfr-testing-deployment.md` §6
describe the target shape (per-PR: format/lint/type-check/tests/dependency
scan/image build; on main: build → deploy staging → smoke test → promote →
rolling deploy with automatic rollback on failed `/readyz`). This folder is
the natural home for that pipeline definition once it exists — nothing here
yet encodes it.
