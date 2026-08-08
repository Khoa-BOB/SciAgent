"""Smoke test proving the app wiring (routers, error handlers) works end to
end. /healthz needs no Neo4j and no auth, so it's safe to run without a live
database -- see specs/04-kg-service-nfr-testing-deployment.md §5.
"""

from fastapi.testclient import TestClient

from kg_service.main import app


def test_healthz_ok() -> None:
    with TestClient(app) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
