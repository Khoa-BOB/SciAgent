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
