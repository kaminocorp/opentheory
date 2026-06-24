"""DB-backed tests for the 0.6.1 verified-identity write path.

Covers: JIT provisioning of exactly one ``Actor`` from a verified bearer JWT (idempotent on
the unique ``external_id``); the ``401`` matrix (missing / malformed / expired / wrong-audience
token); the ``internal`` role grant from the email allowlist; the dev-header path surviving
behind ``auth_dev_header_enabled``; and an existing write flow attributing to the JIT actor.
These run only when a database is configured (see conftest.py); else they skip.
"""

import time

import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import settings
from app.models.actor import Actor
from app.models.contribution import Contribution

# >= 32 bytes so PyJWT's HS256 key-length check stays quiet.
TEST_SECRET = "test-jwt-secret-please-change-0123456789abcdef"
INTERNAL_EMAIL = "insider@kamino.ai"


@pytest.fixture
def auth_settings(monkeypatch: pytest.MonkeyPatch):
    """Configure verified-token auth for a test (auto-restored after)."""
    monkeypatch.setattr(settings, "supabase_jwt_secret", TEST_SECRET)
    monkeypatch.setattr(settings, "supabase_jwt_audience", "authenticated")
    monkeypatch.setattr(settings, "internal_actor_emails", [INTERNAL_EMAIL])
    return settings


def _mint(
    sub: str,
    *,
    secret: str = TEST_SECRET,
    email: str | None = None,
    name: str | None = None,
    aud: str = "authenticated",
    exp_delta: int = 3600,
) -> str:
    now = int(time.time())
    payload: dict = {"sub": sub, "aud": aud, "iat": now, "exp": now + exp_delta}
    if email is not None:
        payload["email"] = email
    if name is not None:
        payload["user_metadata"] = {"name": name}
    return jwt.encode(payload, secret, algorithm="HS256")


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _project(client: AsyncClient, slug: str = "auth-project") -> str:
    resp = await client.post(
        "/api/v1/projects",
        json={"title": "Auth Project", "slug": slug, "question": "What is X?"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_valid_token_jit_provisions_one_actor_and_is_idempotent(
    client: AsyncClient, session_factory: async_sessionmaker, auth_settings
) -> None:
    token = _mint("idp-subject-1", email="ada@example.com", name="Ada Lovelace")

    first = await client.get("/api/v1/me", headers=_bearer(token))
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["external_id"] == "idp-subject-1"
    assert body["display_name"] == "Ada Lovelace"
    assert body["type"] == "human"
    assert body["roles"] == []
    actor_id = body["id"]

    # A second request with the same subject reuses the same actor (no duplicate).
    second = await client.get("/api/v1/me", headers=_bearer(token))
    assert second.status_code == 200
    assert second.json()["id"] == actor_id

    async with session_factory() as session:
        rows = (
            await session.execute(select(Actor).where(Actor.external_id == "idp-subject-1"))
        ).scalars().all()
        assert len(rows) == 1
        assert str(rows[0].id) == actor_id
        # Email is captured into actor_metadata (not a column).
        assert rows[0].actor_metadata.get("email") == "ada@example.com"


async def test_internal_email_provisions_internal_role(
    client: AsyncClient, auth_settings
) -> None:
    internal = await client.get(
        "/api/v1/me", headers=_bearer(_mint("idp-internal", email=INTERNAL_EMAIL))
    )
    assert internal.status_code == 200
    assert internal.json()["roles"] == ["internal"]

    # A different-cased internal email still matches (allowlist compares case-insensitively).
    cased = await client.get(
        "/api/v1/me", headers=_bearer(_mint("idp-internal-2", email=INTERNAL_EMAIL.upper()))
    )
    assert cased.status_code == 200
    assert cased.json()["roles"] == ["internal"]

    outsider = await client.get(
        "/api/v1/me", headers=_bearer(_mint("idp-outsider", email="someone@elsewhere.com"))
    )
    assert outsider.status_code == 200
    assert outsider.json()["roles"] == []


async def test_token_401_matrix(
    client: AsyncClient, auth_settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    # malformed token -> 401
    bad = await client.get("/api/v1/me", headers=_bearer("not-a-jwt"))
    assert bad.status_code == 401

    # expired token -> 401
    expired = await client.get(
        "/api/v1/me", headers=_bearer(_mint("idp-x", exp_delta=-10))
    )
    assert expired.status_code == 401

    # wrong audience -> 401
    wrong_aud = await client.get(
        "/api/v1/me", headers=_bearer(_mint("idp-x", aud="some-other-audience"))
    )
    assert wrong_aud.status_code == 401

    # wrong signing secret -> 401
    forged = await client.get(
        "/api/v1/me",
        headers=_bearer(_mint("idp-x", secret="a-different-secret-also-32-bytes-long-xx")),
    )
    assert forged.status_code == 401

    # missing token, with the dev header path OFF -> 401 (production posture)
    monkeypatch.setattr(settings, "auth_dev_header_enabled", False)
    missing = await client.get("/api/v1/me")
    assert missing.status_code == 401


async def test_write_flow_attributes_to_jit_actor(
    client: AsyncClient, session_factory: async_sessionmaker, auth_settings
) -> None:
    token = _mint("idp-writer", email="writer@example.com", name="Grace")
    project_id = await _project(client)

    me = await client.get("/api/v1/me", headers=_bearer(token))
    actor_id = me.json()["id"]

    thread = await client.post(
        f"/api/v1/projects/{project_id}/threads",
        json={"title": "T", "question": "q?"},
        headers=_bearer(token),
    )
    assert thread.status_code == 201, thread.text

    # The create_thread contribution is attributed to the JIT actor (provenance unchanged).
    async with session_factory() as session:
        contribs = (
            await session.execute(
                select(Contribution).where(Contribution.action == "create_thread")
            )
        ).scalars().all()
        assert len(contribs) == 1
        assert str(contribs[0].actor_id) == actor_id


async def test_dev_header_path_survives_behind_flag(
    client: AsyncClient, auth_settings
) -> None:
    # auth_dev_header_enabled is True process-wide in tests (conftest): the bootstrap +
    # X-Dev-Actor-Id path still works for local/test parity.
    actor = await client.post(
        "/api/v1/actors", json={"type": "human", "display_name": "Dev"}
    )
    assert actor.status_code == 201, actor.text
    actor_id = actor.json()["id"]
    assert actor.json()["roles"] == []

    project_id = await _project(client, slug="dev-header-project")
    thread = await client.post(
        f"/api/v1/projects/{project_id}/threads",
        json={"title": "T", "question": "q?"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert thread.status_code == 201, thread.text


async def test_actor_bootstrap_disabled_when_flag_off(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "auth_dev_header_enabled", False)
    resp = await client.post(
        "/api/v1/actors", json={"type": "human", "display_name": "Nope"}
    )
    assert resp.status_code == 404


async def test_dev_bootstrap_can_seed_internal_role(client: AsyncClient) -> None:
    # The dev bootstrap may seed roles directly (used by the funding tests in 0.6.3).
    resp = await client.post(
        "/api/v1/actors",
        json={"type": "human", "display_name": "Insider", "roles": ["internal"]},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["roles"] == ["internal"]
