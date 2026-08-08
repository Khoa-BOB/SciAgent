"""Structured error model, see specs/02-kg-service-architecture.md §5.

Every error response has the shape {"error": {"code", "message", "details"}}.
`code` is a fixed, growing-only enum so callers can branch on it instead of
parsing `message`.
"""

from enum import StrEnum

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class ErrorCode(StrEnum):
    PAPER_NOT_FOUND = "PAPER_NOT_FOUND"
    EMBEDDING_NOT_AVAILABLE = "EMBEDDING_NOT_AVAILABLE"
    EMPTY_QUERY = "EMPTY_QUERY"
    INVALID_EMBEDDING_DIMENSION = "INVALID_EMBEDDING_DIMENSION"
    CATEGORY_NOT_FOUND = "CATEGORY_NOT_FOUND"
    INVALID_YEAR_RANGE = "INVALID_YEAR_RANGE"
    EMPTY_PAPER_IDS = "EMPTY_PAPER_IDS"
    UNKNOWN_ENTITY_TYPE = "UNKNOWN_ENTITY_TYPE"
    ENTITY_NOT_FOUND = "ENTITY_NOT_FOUND"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    NEO4J_UNAVAILABLE = "NEO4J_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    INGEST_FILE_TOO_LARGE = "INGEST_FILE_TOO_LARGE"
    INGEST_FILE_EMPTY = "INGEST_FILE_EMPTY"
    INGEST_FILE_INVALID_JSONL = "INGEST_FILE_INVALID_JSONL"
    INGEST_JOB_NOT_FOUND = "INGEST_JOB_NOT_FOUND"
    INGEST_STORAGE_UNAVAILABLE = "INGEST_STORAGE_UNAVAILABLE"
    INGEST_QUEUE_UNAVAILABLE = "INGEST_QUEUE_UNAVAILABLE"


class ApiError(Exception):
    def __init__(self, status_code: int, code: ErrorCode, message: str, details: dict | None = None):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code.value, "message": exc.message, "details": exc.details}},
        )

    @app.exception_handler(NotImplementedError)
    async def handle_not_implemented(request: Request, exc: NotImplementedError) -> JSONResponse:
        # Distinguishes "not built yet" (scaffold stub) from a real 500 bug --
        # see kg_service/services/*.py.
        return JSONResponse(
            status_code=501,
            content={"error": {"code": "NOT_IMPLEMENTED", "message": str(exc) or "Not implemented.", "details": {}}},
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        # Never leak internal exception details/stack traces to the caller --
        # specs/04-kg-service-nfr-testing-deployment.md §3. Real detail goes
        # to server-side structured logs (wire up logging in main.py).
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": ErrorCode.INTERNAL_ERROR.value,
                    "message": "An unexpected error occurred.",
                    "details": {},
                }
            },
        )
