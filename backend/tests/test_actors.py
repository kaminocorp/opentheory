"""DB-free regression tests for the actor- and account-endpoint production gates (0.6.1; 0.7.0).

``GET``/``POST /actors`` and ``GET``/``POST /accounts`` are all retired in production. With
Account-owns-Actor the PII split is: ``ActorRead`` still exposes ``actor_metadata`` (the verified
email, since JIT provisioning), and ``AccountRead`` exposes ``external_id`` + email + ``roles`` (the
0.6.1 email/identity-harvest leak class, *moved here with those fields*). So an open list on either
is a leak. Every handler raises ``404`` when ``auth_dev_header_enabled`` is off — *before* touching
the database — so these guards need no Postgres and run in the default suite.

Without these, removing any ``if not settings.auth_dev_header_enabled`` guard would reopen the leak
and fail no existing test: every other actor/account test runs with the dev flag on (the ``client``
fixture, which also skips without a database).
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


def test_account_list_disabled_when_flag_off(
    dbfree_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # AccountRead carries external_id + the verified email + roles — the 0.6.1 PII class moved here.
    # Production posture: dev flag off, so the account list is 404, gated before any DB access.
    monkeypatch.setattr(settings, "auth_dev_header_enabled", False)

    resp = dbfree_client.get("/api/v1/accounts")

    assert resp.status_code == 404, resp.text


def test_account_create_disabled_when_flag_off(
    dbfree_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The open account bootstrap survives only behind the dev flag; in production accounts are
    # JIT-provisioned from a verified token on sign-in, so the create route is 404.
    monkeypatch.setattr(settings, "auth_dev_header_enabled", False)

    resp = dbfree_client.post("/api/v1/accounts", json={"display_name": "Nope"})

    assert resp.status_code == 404, resp.text
