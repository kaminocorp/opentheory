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


def test_unauthenticated_project_update_is_rejected(
    dbfree_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # PATCH /projects/{id} (0.8.1) is owner/admin-gated; an unauthenticated request is rejected by
    # the ActingActor dependency *before* the handler touches the DB (so the 403 member check never
    # runs). The project id never resolves — the 401 must come from the auth gate, not a 404.
    monkeypatch.setattr(settings, "auth_dev_header_enabled", False)

    resp = dbfree_client.patch(
        "/api/v1/projects/00000000-0000-0000-0000-000000000000",
        json={"title": "Renamed"},
    )

    assert resp.status_code == 401, resp.text


def test_agent_model_catalog_is_public(dbfree_client: TestClient) -> None:
    # The curated OpenRouter catalog (0.8.10) is static reference data with no project scope and no
    # auth — it populates the assignment dropdown for anyone viewing a project. No DB touched.
    resp = dbfree_client.get("/api/v1/agent-models/catalog")

    assert resp.status_code == 200, resp.text
    catalog = resp.json()
    assert isinstance(catalog, list) and catalog, catalog
    first = catalog[0]
    assert {"id", "name", "provider"} <= first.keys(), first
    # The dropdown can only offer ids the write path will accept — so every catalog id is valid.
    from app.core.openrouter_models import VALID_MODEL_IDS

    assert {entry["id"] for entry in catalog} <= VALID_MODEL_IDS


def test_unauthenticated_agent_models_update_is_rejected(
    dbfree_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # PUT /projects/{id}/agent-models (0.8.10) is owner/admin-gated like the metadata PATCH; an
    # unauthenticated request is rejected by the ActingActor dependency before the handler runs, so
    # the project id never has to resolve (the 401 is the auth gate, not a 404).
    monkeypatch.setattr(settings, "auth_dev_header_enabled", False)

    resp = dbfree_client.put(
        "/api/v1/projects/00000000-0000-0000-0000-000000000000/agent-models",
        json={"research_lead": "anthropic/claude-opus-4.1"},
    )

    assert resp.status_code == 401, resp.text
