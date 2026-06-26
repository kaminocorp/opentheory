"""DB-free regression tests for the actor-endpoint production gate (0.6.1).

``GET`` and ``POST /actors`` are both retired in production: ``ActorRead`` exposes
``external_id`` + ``actor_metadata`` (the verified email, since JIT provisioning) + ``roles``,
so an open list is an email/identity-harvesting leak. Both handlers raise ``404`` when
``auth_dev_header_enabled`` is off — *before* touching the database — so these guards need no
Postgres and run in the default suite.

Without these, removing either ``if not settings.auth_dev_header_enabled`` guard would reopen
the leak and fail no existing test: every other actor test runs with the dev flag on (the
``client`` fixture, which also skips without a database).
"""

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings


def test_actor_list_disabled_when_flag_off(
    dbfree_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Production posture: the dev flag is off, so the actor list (which would leak every
    # actor's email, IdP subject, and roles to an anonymous caller) is 404 — gated in the
    # handler before any DB access.
    monkeypatch.setattr(settings, "auth_dev_header_enabled", False)

    resp = dbfree_client.get("/api/v1/actors")

    assert resp.status_code == 404, resp.text


def test_actor_create_disabled_when_flag_off(
    dbfree_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The open bootstrap survives only behind the dev flag; in production actors are
    # JIT-provisioned from a verified token, so the create route is 404.
    monkeypatch.setattr(settings, "auth_dev_header_enabled", False)

    resp = dbfree_client.post("/api/v1/actors", json={"type": "human", "display_name": "Nope"})

    assert resp.status_code == 404, resp.text
