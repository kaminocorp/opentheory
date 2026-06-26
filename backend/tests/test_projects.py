"""Route-level auth-gate tests for the project and funding endpoints.

These gates — ``POST /projects`` (0.6.3) and ``POST /projects/{id}/funding`` (0.6.0) both
require a verified ``ActingActor`` — reject an unauthenticated request inside the dependency,
*before* the handler touches the database. So they need no Postgres and run in the default
(DB-less) suite, unlike the create-path tests in the DB-backed files. They are the direct
regression tests for the gates: without them, removing the ``ActingActor`` dependency from a
handler would fail no existing test (the DB-backed suites all send a credential and skip without
Postgres). The 403/422 *funding* gates (internal-role, stripe-rejection) fire only after the
authenticated actor and project row resolve, so they remain DB-backed in ``test_funding.py``.
"""

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings


def test_unauthenticated_project_create_is_rejected(
    dbfree_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Production posture: the dev-header fallback is off, so no credential resolves.
    # (conftest enables it process-wide for the attribution suite; turn it off here.)
    monkeypatch.setattr(settings, "auth_dev_header_enabled", False)

    resp = dbfree_client.post(
        "/api/v1/projects",
        json={"title": "Unauthorized", "slug": "unauthorized", "question": "May I?"},
    )

    # Rejected by the ActingActor dependency before the handler runs — no DB access needed.
    assert resp.status_code == 401, resp.text


def test_unauthenticated_funding_create_is_rejected(
    dbfree_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The funding write path is auth-gated too; a valid body (the project id never resolves —
    # the request is rejected first) confirms the 401 comes from ActingActor, not validation.
    monkeypatch.setattr(settings, "auth_dev_header_enabled", False)

    resp = dbfree_client.post(
        "/api/v1/projects/00000000-0000-0000-0000-000000000000/funding",
        json={"amount": "100.00"},
    )

    assert resp.status_code == 401, resp.text
