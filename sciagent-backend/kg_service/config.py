"""Env-based config, matching the pattern already used by sciagent-KG
(src/config.py): plain os.getenv + dotenv, validated up front with a clear
error naming what's missing -- no framework-level settings magic.
"""

import os

from dotenv import load_dotenv

load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

# Comma-separated allowlist of service-to-service API keys, see
# specs/02-kg-service-architecture.md §6. Never commit real values --
# set this in sciagent-backend/.env or the deployment secret manager.
ALLOWED_SERVICE_KEYS = {
    key.strip()
    for key in os.getenv("KG_SERVICE_ALLOWED_KEYS", "").split(",")
    if key.strip()
}

# Separate, smaller allowlist for the /v1/ingest-jobs write path -- see
# specs/02-kg-service-architecture.md §8. A caller holding a read-only
# KG_SERVICE_ALLOWED_KEYS key must NOT be able to trigger an ingest job.
WRITE_ALLOWED_SERVICE_KEYS = {
    key.strip()
    for key in os.getenv("KG_SERVICE_WRITE_ALLOWED_KEYS", "").split(",")
    if key.strip()
}

# MinIO (S3-compatible) staging for uploaded ingest files, see
# specs/02-kg-service-architecture.md §8. Read by both the API process
# (uploads) and the worker process (downloads) -- unlike KG_WRITE_NEO4J_*,
# this is not a privileged credential, so sharing it across both processes
# is fine.
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").strip().lower() == "true"
MINIO_INGEST_BUCKET = os.getenv("MINIO_INGEST_BUCKET", "kg-ingest-uploads")

# Redis-backed job queue (RQ) connecting the API process (enqueues) to the
# worker process (dequeues and does the actual write). See
# specs/02-kg-service-architecture.md §8.
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Reject an ingest upload above this size before it ever reaches MinIO or
# the worker -- see specs/03-kg-service-api-spec.md §8.
MAX_INGEST_FILE_BYTES = int(os.getenv("MAX_INGEST_FILE_BYTES", str(200 * 1024 * 1024)))


def validate_config() -> None:
    """Raise a clear error naming any missing required env var(s)."""
    missing = [
        name
        for name, value in (
            ("NEO4J_URI", NEO4J_URI),
            ("NEO4J_USERNAME", NEO4J_USERNAME),
            ("NEO4J_PASSWORD", NEO4J_PASSWORD),
        )
        if not value
    ]
    if missing:
        raise EnvironmentError(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            "Set them in sciagent-backend/.env -- see .env.example. "
            "This service expects READ-ONLY Neo4j credentials, separate from "
            "sciagent-KG's ingestion/extraction credentials "
            "(specs/04-kg-service-nfr-testing-deployment.md §3)."
        )
    if not ALLOWED_SERVICE_KEYS:
        raise EnvironmentError(
            "KG_SERVICE_ALLOWED_KEYS is empty -- set at least one caller API "
            "key in sciagent-backend/.env, or no request will ever authenticate."
        )
