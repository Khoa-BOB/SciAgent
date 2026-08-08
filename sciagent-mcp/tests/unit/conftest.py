"""Shared fixture: a fake KGServiceClient wired into mcp_service.app's module-
level singleton, the same way the real lifespan (mcp_service/app.py) does it
at server startup. Tool modules call get_kg_client() at call time, so
patching the module global here is enough -- no need to run the server or
its lifespan for these tests.
"""

from unittest.mock import AsyncMock

import pytest

import mcp_service.app as app_module


@pytest.fixture
def fake_kg_client(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    client = AsyncMock()
    monkeypatch.setattr(app_module, "_kg_client", client)
    return client
