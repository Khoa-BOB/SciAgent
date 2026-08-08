"""specs/02-mcp-architecture.md §7 -- KG Service error -> KGServiceError mapping."""

import httpx
import pytest

from mcp_service.errors import (
    CAPABILITY_NOT_AVAILABLE,
    KG_SERVICE_UNAVAILABLE,
    KGServiceError,
    error_from_exception,
    error_from_response,
)


def _response(status_code: int, json_body: dict | None = None, text: str = "") -> httpx.Response:
    request = httpx.Request("GET", "http://kg-service.test/v1/papers/2401.00001")
    if json_body is not None:
        return httpx.Response(status_code, json=json_body, request=request)
    return httpx.Response(status_code, text=text, request=request)


def test_error_from_response_passes_through_code_and_message() -> None:
    response = _response(404, {"error": {"code": "PAPER_NOT_FOUND", "message": "no such paper"}})

    error = error_from_response(response)

    assert error.status_code == 404
    assert error.code == "PAPER_NOT_FOUND"
    assert error.message == "no such paper"


def test_error_from_response_maps_501_to_capability_not_available() -> None:
    response = _response(501, {"error": {"code": "NOT_IMPLEMENTED", "message": "search_fulltext not built yet"}})

    error = error_from_response(response)

    assert error.status_code == 501
    assert error.code == CAPABILITY_NOT_AVAILABLE
    assert "not built yet" in error.message


def test_error_from_response_handles_non_json_body() -> None:
    response = _response(502, text="upstream timeout")

    error = error_from_response(response)

    assert error.code == "UNKNOWN_ERROR"
    assert error.message == "upstream timeout"


def test_error_from_exception_maps_to_service_unavailable() -> None:
    exc = httpx.ConnectError("connection refused")

    error = error_from_exception(exc)

    assert error.status_code == 503
    assert error.code == KG_SERVICE_UNAVAILABLE
    assert "connection refused" in error.message


def test_kg_service_error_str_carries_code_and_message() -> None:
    error = KGServiceError(422, "INVALID_EMBEDDING_DIMENSION", "expected 768 dims")

    assert str(error) == "INVALID_EMBEDDING_DIMENSION: expected 768 dims"


def test_kg_service_error_raises_cleanly() -> None:
    with pytest.raises(KGServiceError) as exc_info:
        raise KGServiceError(404, "PAPER_NOT_FOUND", "no such paper")
    assert exc_info.value.status_code == 404
