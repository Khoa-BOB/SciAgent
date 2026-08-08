"""The ingest job executed by kg_service.worker (a separate process from
kg_service.main:app) -- specs/02-kg-service-architecture.md §8.

Credential boundary: this module is the only place in sciagent-backend that
builds a *read-write* Neo4j driver, from KG_WRITE_NEO4J_* env vars that
kg_service.deps/kg_service.config never read. The API process (kg_service.main)
enqueues work here but never imports this module's driver-building code path
at request time -- see kg_service/services/ingest.py's local `from
kg_service.jobs import run_ingest_job` (deferred so importing kg_service.main
doesn't pull in a write driver). In deployment, only the worker container's
environment should ever be given KG_WRITE_NEO4J_* values; the API container's
should not, so the boundary is enforced by which process has the secret, not
just by code convention. See specs/04-kg-service-nfr-testing-deployment.md §3.

Also holds the optional entity-extraction follow-up (run_ingest_job's
run_extraction flag) -- see _run_extraction_followup's docstring and
specs/02-kg-service-architecture.md §8.5 for why it's opt-in and how it
resolves this job's new mentions against every existing canonical entity in
Neo4j (via a stored embedding on each entity node) without re-reading
sciagent-KG's entire historical shards directory on every job.
"""

import json
import logging
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

import kg_service.kg_path  # noqa: F401  -- must run before importing sciagent-KG modules
from neo4j import Driver, GraphDatabase

from kg_service.config import MINIO_INGEST_BUCKET
from kg_service.deps import get_minio_client

logger = logging.getLogger(__name__)

_embedding_model = None  # lazy, cached per worker process -- see _get_embedding_model()
_extraction_client = None  # lazy, cached per worker process -- see _get_extraction_client()

# Worker-only extraction config -- like KG_WRITE_NEO4J_*, deliberately kept
# out of kg_service.config so the API process's config surface never implies
# it needs an LLM backend. Only read here, and only exercised when a caller
# explicitly passes run_extraction=True -- matches sciagent-KG's own
# non-goal against automatic, unattended extraction
# (sciagent-KG/specs/01-requirements.md §4).
_EXTRACTION_BASE_URL = os.getenv("EXTRACTION_BASE_URL", "http://localhost:11434/v1")
_EXTRACTION_MODEL = os.getenv("EXTRACTION_MODEL", "zephyr:latest")
_EXTRACTION_API_KEY = os.getenv("EXTRACTION_API_KEY")


def _write_driver() -> Driver:
    """Read-write Neo4j credential, distinct from kg_service.deps.get_driver()'s
    read-only one. Required env vars are only ever set on the worker process."""
    missing = [
        name
        for name in ("KG_WRITE_NEO4J_URI", "KG_WRITE_NEO4J_USERNAME", "KG_WRITE_NEO4J_PASSWORD")
        if not os.getenv(name)
    ]
    if missing:
        raise EnvironmentError(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            "The ingest worker needs its own read-write Neo4j credential, separate "
            "from kg_service's read-only one -- see sciagent-backend/.env.worker.example."
        )
    return GraphDatabase.driver(
        os.environ["KG_WRITE_NEO4J_URI"],
        auth=(os.environ["KG_WRITE_NEO4J_USERNAME"], os.environ["KG_WRITE_NEO4J_PASSWORD"]),
    )


def _get_embedding_model():
    """Loaded once per worker process and reused across jobs -- same reasoning
    as kg_service.deps.get_vector_search() on the read side: reloading a
    SentenceTransformer per job would dominate every ingest job's runtime."""
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer

        from src.ingestion.embeddings.index_papers import MODEL_NAME

        _embedding_model = SentenceTransformer(MODEL_NAME)
    return _embedding_model


def _get_extraction_client():
    """Loaded once per worker process -- same reasoning as
    _get_embedding_model(). Only ever constructed if a job actually requests
    run_extraction=True, so a worker that never gets that flag never opens
    an LLM client at all."""
    global _extraction_client
    if _extraction_client is None:
        from src.extraction.llm_client import ExtractionClient, resolve_api_key

        _extraction_client = ExtractionClient(
            base_url=_EXTRACTION_BASE_URL,
            model=_EXTRACTION_MODEL,
            api_key=resolve_api_key(_EXTRACTION_API_KEY, _EXTRACTION_BASE_URL),
        )
    return _extraction_client


def _build_extraction_shard(local_path: Path, output_path: Path) -> list[str]:
    """Build an (arxiv_id, title, abstract) shard for exactly this job's
    papers from the same upload already downloaded for ingestion -- avoids a
    second Neo4j round trip. Mirrors export_papers()'s own eligibility rule
    (title + non-blank abstract required) so extraction never sees a paper
    it can't do anything useful with."""
    arxiv_ids: list[str] = []
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with local_path.open(encoding="utf-8") as upload_file, output_path.open("w", encoding="utf-8") as shard_file:
        for line in upload_file:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            arxiv_id = str(record.get("id", "")).strip()
            title = str(record.get("title") or "").strip()
            abstract = str(record.get("abstract") or "").strip()
            if not arxiv_id or not title or not abstract:
                continue
            shard_file.write(
                json.dumps({"arxiv_id": arxiv_id, "title": title, "abstract": abstract}, ensure_ascii=False) + "\n"
            )
            arxiv_ids.append(arxiv_id)
    return arxiv_ids


def _run_extraction_followup(local_path: Path, driver: Driver) -> dict[str, Any]:
    """Optional follow-up to ingestion, only called when a caller explicitly
    passes run_extraction=True: extract Method/Dataset/ResearchTopic entities
    for exactly the papers this job just loaded.

    Resolve is seeded with every canonical entity already in Neo4j that has
    a stored embedding (fetch_existing_clusters) -- so a new mention gets a
    real chance to cluster into an already-existing canonical entity via
    cosine similarity + the acronym fallback in resolve.py, without
    re-embedding or re-reading sciagent-KG's entire historical shards
    directory on every job. This only works to the extent the existing
    corpus has been backfilled with embeddings (merge.backfill_entity_embeddings)
    -- an un-backfilled entity is invisible to this seed and won't be a
    merge candidate until it is. See specs/02-kg-service-architecture.md §8.5.

    Because resolve() only ever processes this job's own shard (not the
    whole corpus), every row it returns already belongs to this job -- no
    separate filtering step is needed before merge, unlike the old
    full-corpus-resolve approach this replaced.
    """
    from src.config import NEO4J_DATABASE
    from src.extraction.export import DEFAULT_OUTPUT_DIR as SHARDS_DIR
    from src.extraction.extract import run_extraction as run_llm_extraction
    from src.extraction.merge import fetch_existing_clusters, merge_resolved
    from src.extraction.resolve import DEFAULT_SIMILARITY_THRESHOLD, resolve

    # A job-scoped subdirectory, not the flat top-level SHARDS_DIR -- resolve()
    # globs every *.extracted.jsonl in whatever directory it's given, and this
    # job only wants to resolve its OWN new mentions (against the existing_clusters
    # seed below), not every historical shard the full corpus has ever produced.
    # Still lives under the persistent data/extraction/ tree, though, so the raw
    # extracted output survives on disk like every other stage's output does.
    job_dir = SHARDS_DIR / "ingest-jobs" / uuid.uuid4().hex[:12]
    shard_path = job_dir / "shard.jsonl"
    extracted_path = job_dir / "shard.extracted.jsonl"

    arxiv_ids = _build_extraction_shard(local_path, shard_path)
    if not arxiv_ids:
        return {"papers_extracted": 0, "entities_written": 0, "relationships_written": 0}

    extracted = run_llm_extraction(shard_path, extracted_path, _get_extraction_client(), resume=False)

    existing_clusters = fetch_existing_clusters(driver, NEO4J_DATABASE)
    resolved_rows, new_embeddings = resolve(
        job_dir,
        threshold=DEFAULT_SIMILARITY_THRESHOLD,
        model=_get_embedding_model(),
        existing_clusters=existing_clusters,
    )

    entities_written, relationships_written = merge_resolved(
        driver, NEO4J_DATABASE, resolved_rows, new_embeddings=new_embeddings
    )

    logger.info(
        "Extraction follow-up for %s: extracted=%d entities=%d relationships=%d",
        job_dir.name, extracted, entities_written, relationships_written,
    )
    return {
        "papers_extracted": extracted,
        "entities_written": entities_written,
        "relationships_written": relationships_written,
    }


def run_ingest_job(object_key: str, run_extraction: bool = False) -> dict[str, Any]:
    """RQ entrypoint. Downloads the staged upload from MinIO, then runs the
    exact same idempotent stages sciagent-KG's own CLI runs (schema -> load ->
    embed -> validate) against it -- see sciagent-KG/specs/02-architecture.md.
    Nothing here reimplements ingestion logic; it only orchestrates it.

    If run_extraction is True, also runs entity extraction for exactly the
    papers this job loaded as a best-effort follow-up (see
    _run_extraction_followup) -- a failure there is recorded in the result's
    extraction.error field rather than raised, since ingestion has already
    committed successfully by the time extraction runs and a downstream LLM
    hiccup shouldn't retroactively mark that as a failed job.
    """
    from src.ingestion.embeddings.index_papers import run_embedding
    from src.ingestion.load_metadata import load_metadata
    from src.ingestion.schema import apply_schema
    from src.ingestion.validate import run_validation

    minio_client = get_minio_client()

    with tempfile.TemporaryDirectory() as tmpdir:
        local_path = Path(tmpdir) / "upload.jsonl"
        minio_client.fget_object(MINIO_INGEST_BUCKET, object_key, str(local_path))

        driver = _write_driver()
        try:
            apply_schema(driver)
            # resume=False: each upload gets its own temp path, so there is no
            # prior checkpoint to resume from -- see checkpoint.py's per-path keying.
            loaded = load_metadata(local_path, driver, resume=False)
            embedded = run_embedding(driver, _get_embedding_model(), only_missing=True)
            results = run_validation(driver)
            violations = {result.check.name: result.violations for result in results if result.violations > 0}

            logger.info(
                "Ingest job for %s: loaded=%d embedded=%d violations=%s", object_key, loaded, embedded, violations
            )
            result: dict[str, Any] = {
                "loaded": loaded,
                "embedded": embedded,
                "validation_passed": not violations,
                "validation_violations": violations,
            }

            if run_extraction:
                try:
                    result["extraction"] = _run_extraction_followup(local_path, driver)
                except Exception as error:
                    logger.exception("Extraction follow-up failed for %s", object_key)
                    result["extraction"] = {
                        "papers_extracted": 0,
                        "entities_written": 0,
                        "relationships_written": 0,
                        "error": str(error),
                    }

            return result
        finally:
            driver.close()
