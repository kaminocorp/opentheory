"""Route-level auth-gate tests for the project endpoints.

The 0.6.3 gate — ``POST /projects`` requires a verified ``ActingActor`` — rejects an
unauthenticated request inside the dependency, *before* the handler touches the database. So
this guard needs no Postgres and runs in the default (DB-less) suite, unlike the create-path
tests in the DB-backed files. It is the direct regression test for the gate: without it,
removing the ``ActingActor`` dependency from ``create_project`` would not fail any existing
test (they all send a credential through the ``_project`` helper).
"""

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import create_app


def test_unauthenticated_project_create_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    # Production posture: the dev-header fallback is off, so no credential resolves.
    # (conftest enables it process-wide for the attribution suite; turn it off here.)
    monkeypatch.setattr(settings, "auth_dev_header_enabled", False)
    client = TestClient(create_app())

    resp = client.post(
        "/api/v1/projects",
        json={"title": "Unauthorized", "slug": "unauthorized", "question": "May I?"},
    )

    # Rejected by the ActingActor dependency before the handler runs — no DB access needed.
    assert resp.status_code == 401, resp.text
