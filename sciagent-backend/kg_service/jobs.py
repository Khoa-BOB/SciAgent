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
"""

import logging
import os
import tempfile
from pathlib import Path
from typing import Any

import kg_service.kg_path  # noqa: F401  -- must run before importing sciagent-KG modules
from neo4j import Driver, GraphDatabase

from kg_service.config import MINIO_INGEST_BUCKET
from kg_service.deps import get_minio_client

logger = logging.getLogger(__name__)

_embedding_model = None  # lazy, cached per worker process -- see _get_embedding_model()


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


def run_ingest_job(object_key: str) -> dict[str, Any]:
    """RQ entrypoint. Downloads the staged upload from MinIO, then runs the
    exact same idempotent stages sciagent-KG's own CLI runs (schema -> load ->
    embed -> validate) against it -- see sciagent-KG/specs/02-architecture.md.
    Nothing here reimplements ingestion logic; it only orchestrates it.
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
            return {
                "loaded": loaded,
                "embedded": embedded,
                "validation_passed": not violations,
                "validation_violations": violations,
            }
        finally:
            driver.close()
