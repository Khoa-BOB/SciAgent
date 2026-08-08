"""Service-to-service auth: a static API key in X-Service-Key, checked
against an allowlist. No end-user auth here -- that's the BFF's job, see
specs/01-kg-service-requirements.md §4 and specs/02-kg-service-architecture.md §6.
"""

from fastapi import Header

from kg_service.config import ALLOWED_SERVICE_KEYS, WRITE_ALLOWED_SERVICE_KEYS
from kg_service.errors import ApiError, ErrorCode


def require_service_key(x_service_key: str | None = Header(default=None)) -> str:
    if not x_service_key or x_service_key not in ALLOWED_SERVICE_KEYS:
        raise ApiError(401, ErrorCode.UNAUTHENTICATED, "Missing or invalid X-Service-Key.")
    return x_service_key


def require_write_service_key(x_service_key: str | None = Header(default=None)) -> str:
    """Separate, smaller allowlist for the /v1/ingest-jobs write path -- a
    caller holding only a read-scoped key must not be able to trigger a
    write. See specs/02-kg-service-architecture.md §8."""
    if not x_service_key or x_service_key not in WRITE_ALLOWED_SERVICE_KEYS:
        raise ApiError(
            401, ErrorCode.UNAUTHENTICATED, "Missing or invalid X-Service-Key for a write-scoped caller."
        )
    return x_service_key
