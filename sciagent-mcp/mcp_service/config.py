"""Env-based config, matching the pattern already used by sciagent-KG and
sciagent-backend: plain os.getenv + dotenv, validated up front with a clear
error naming what's missing -- see specs/04-mcp-nfr-testing-deployment.md §6.
"""

import os

from dotenv import load_dotenv

load_dotenv()

# Outbound credential -- this service's own entry in the KG Service's
# KG_SERVICE_ALLOWED_KEYS allowlist. See specs/02-mcp-architecture.md §6.
KG_SERVICE_BASE_URL = os.getenv("KG_SERVICE_BASE_URL", "http://localhost:8000")
KG_SERVICE_API_KEY = os.getenv("KG_SERVICE_API_KEY", "")

# Inbound credential -- allowlist for the Agent Orchestrator (or any other
# caller) connecting to this service's Streamable HTTP endpoint.
MCP_ALLOWED_KEYS = {key.strip() for key in os.getenv("MCP_ALLOWED_KEYS", "").split(",") if key.strip()}

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8100"))

# Extra Host header values to accept on the /mcp endpoint, beyond the MCP
# SDK's own automatic loopback allowance (127.0.0.1/localhost/[::1]) -- see
# mcp_service/server.py. Required when this service sits behind a reverse
# proxy or is reached by a non-loopback hostname in production, otherwise
# every request 421s. Comma-separated; "host:*" matches any port.
MCP_ALLOWED_HOSTS = {h.strip() for h in os.getenv("MCP_ALLOWED_HOSTS", "").split(",") if h.strip()}
MCP_ALLOWED_ORIGINS = {o.strip() for o in os.getenv("MCP_ALLOWED_ORIGINS", "").split(",") if o.strip()}


def validate_config() -> None:
    """Raise a clear error naming any missing required config. Called at
    process startup (mcp_service/server.py's main()), not at import time --
    lets tests import config/app modules without needing real env vars."""
    missing = []
    if not KG_SERVICE_API_KEY:
        missing.append("KG_SERVICE_API_KEY")
    if missing:
        raise OSError(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            "Set them in sciagent-mcp/.env -- see .env.example."
        )
    if not MCP_ALLOWED_KEYS:
        raise OSError(
            "MCP_ALLOWED_KEYS is empty -- set at least one caller key in "
            "sciagent-mcp/.env, or no Agent Orchestrator request will ever "
            "authenticate against this service."
        )
