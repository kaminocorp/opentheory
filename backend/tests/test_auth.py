"""DB-backed tests for the verified-identity write path (0.6.1; Account-owns-Actor in 0.7.0).

Covers: JIT provisioning of exactly one ``Account`` **and** its one primary ``human`` ``Actor`` from
a verified bearer JWT (idempotent on the unique ``accounts.external_id``); the ``401`` matrix
(missing / malformed / expired / wrong-audience token); the ``internal`` role grant from the email
allowlist landing on the **account**; the partial unique index (one ``human`` per account); the
dev-header path surviving behind ``auth_dev_header_enabled``; and an existing write flow attributing
to the JIT actor. These run only when a database is configured (see conftest.py); else they skip.
"""

import time
from uuid import UUID

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.auth import AuthError, verify_bearer_token
from app.core.config import settings
from app.models.account import Account
from app.models.actor import Actor
from app.models.contribution import Contribution
from app.models.enums import ActorType

# Supabase signs sessions with ES256 (asymmetric). We mint tokens with a throwaway P-256 key
# and inject its public half into the verifier (see auth_settings), so the suite never reaches a
# network JWKS endpoint. `_OTHER_KEY` is a *different* key, for the forged-signature case.
_SIGNING_KEY = ec.generate_private_key(ec.SECP256R1())
_PUBLIC_KEY = _SIGNING_KEY.public_key()
_OTHER_KEY = ec.generate_private_key(ec.SECP256R1())
INTERNAL_EMAIL = "insider@kamino.ai"


@pytest.fixture
def auth_settings(monkeypatch: pytest.MonkeyPatch):
    """Configure verified-token auth for a test (auto-restored after).

    Patches the verifier's signing-key seam to return the test public key (no JWKS fetch), so
    a token minted with ``_SIGNING_KEY`` verifies and one minted with ``_OTHER_KEY`` fails on
    signature — exercising the real ``jwt.decode`` path without network I/O.
    """
    monkeypatch.setattr(settings, "supabase_jwt_audience", "authenticated")
    monkeypatch.setattr(settings, "internal_actor_emails", [INTERNAL_EMAIL])
    monkeypatch.setattr("app.core.auth._signing_key", lambda _token: _PUBLIC_KEY)
    return settings


def _mint(
    sub: str,
    *,
    key: ec.EllipticCurvePrivateKey = _SIGNING_KEY,
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
    return jwt.encode(payload, key, algorithm="ES256", headers={"kid": "test-key"})


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --- DB-free unit tests of the ES256 verifier itself (no IdP, no database) ----------------
# These call verify_bearer_token directly, so they run in the default (DB-free) suite and give
# real coverage of the signature/audience/expiry path independent of provisioning. The signing
# key is injected locally — they never reach a network JWKS endpoint.


def _inject_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "supabase_jwt_audience", "authenticated")
    monkeypatch.setattr("app.core.auth._signing_key", lambda _token: _PUBLIC_KEY)


def test_verifier_accepts_valid_es256_token(monkeypatch: pytest.MonkeyPatch) -> None:
    _inject_key(monkeypatch)
    identity = verify_bearer_token(_mint("sub-1", email="ada@example.com", name="Ada"))
    assert identity.subject == "sub-1"
    assert identity.email == "ada@example.com"
    assert identity.display_name == "Ada"


def test_verifier_falls_back_to_email_then_subject_for_display_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _inject_key(monkeypatch)
    assert verify_bearer_token(_mint("sub-2", email="e@x.com")).display_name == "e@x.com"
    assert verify_bearer_token(_mint("sub-3")).display_name == "sub-3"


@pytest.mark.parametrize(
    "token_factory",
    [
        pytest.param(lambda: _mint("sub", key=_OTHER_KEY), id="wrong-signing-key"),
        pytest.param(lambda: _mint("sub", exp_delta=-10), id="expired"),
        pytest.param(lambda: _mint("sub", aud="someone-else"), id="wrong-audience"),
        pytest.param(lambda: "not-a-jwt", id="malformed"),
    ],
)
def test_verifier_rejects_bad_tokens(
    monkeypatch: pytest.MonkeyPatch, token_factory
) -> None:
    _inject_key(monkeypatch)
    with pytest.raises(AuthError):
        verify_bearer_token(token_factory())


def test_verifier_rejects_when_auth_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    # No JWKS URL and no project URL -> the real _signing_key raises AuthError before any fetch.
    monkeypatch.setattr(settings, "supabase_jwks_url", None)
    monkeypatch.setattr(settings, "supabase_project_url", None)
    with pytest.raises(AuthError):
        verify_bearer_token(_mint("sub"))


async def _project(client: AsyncClient, slug: str = "auth-project") -> str:
    # Project creation now requires an acting actor; bootstrap a dev actor for the header
    # (auth_dev_header_enabled is True process-wide in tests — see conftest).
    actor = await client.post(
        "/api/v1/actors", json={"type": "human", "display_name": "Author"}
    )
    assert actor.status_code == 201, actor.text
    resp = await client.post(
        "/api/v1/projects",
        json={"title": "Auth Project", "slug": slug, "question": "What is X?"},
        headers={"X-Dev-Actor-Id": actor.json()["id"]},
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
    assert body["display_name"] == "Ada Lovelace"
    assert body["type"] == "human"
    # external_id + roles moved to the nested account (Account-owns-Actor); /me serializes MeRead.
    assert body["account"]["external_id"] == "idp-subject-1"
    assert body["account"]["roles"] == []
    actor_id = body["id"]
    account_id = body["account"]["id"]

    # A second request with the same subject reuses the same actor AND account (no duplicate).
    second = await client.get("/api/v1/me", headers=_bearer(token))
    assert second.status_code == 200
    assert second.json()["id"] == actor_id
    assert second.json()["account"]["id"] == account_id

    async with session_factory() as session:
        # Exactly one Account for the subject, and exactly one human Actor owned by it.
        accounts = (
            await session.execute(select(Account).where(Account.external_id == "idp-subject-1"))
        ).scalars().all()
        assert len(accounts) == 1
        assert str(accounts[0].id) == account_id
        assert accounts[0].email == "ada@example.com"  # email promoted onto the principal

        actors = (
            await session.execute(select(Actor).where(Actor.account_id == accounts[0].id))
        ).scalars().all()
        assert len(actors) == 1
        assert str(actors[0].id) == actor_id
        assert actors[0].type == ActorType.HUMAN
        # Email is also mirrored into actor_metadata at provision (kept for back-compat).
        assert actors[0].actor_metadata.get("email") == "ada@example.com"


async def test_internal_email_provisions_internal_role(
    client: AsyncClient, auth_settings
) -> None:
    # Roles are granted on the Account now (Decision #4); /me surfaces them under `account`.
    internal = await client.get(
        "/api/v1/me", headers=_bearer(_mint("idp-internal", email=INTERNAL_EMAIL))
    )
    assert internal.status_code == 200
    assert internal.json()["account"]["roles"] == ["internal"]

    # A different-cased internal email still matches (allowlist compares case-insensitively).
    cased = await client.get(
        "/api/v1/me", headers=_bearer(_mint("idp-internal-2", email=INTERNAL_EMAIL.upper()))
    )
    assert cased.status_code == 200
    assert cased.json()["account"]["roles"] == ["internal"]

    outsider = await client.get(
        "/api/v1/me", headers=_bearer(_mint("idp-outsider", email="someone@elsewhere.com"))
    )
    assert outsider.status_code == 200
    assert outsider.json()["account"]["roles"] == []


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

    # wrong signing key (valid ES256 token signed by a key whose public half isn't ours) -> 401
    forged = await client.get(
        "/api/v1/me",
        headers=_bearer(_mint("idp-x", key=_OTHER_KEY)),
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
    # A bare dev actor is account-less (Decision #8): roles moved to the account, so a dev actor
    # has no principal unless explicitly linked to one.
    assert actor.json()["account_id"] is None

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


async def test_dev_bootstrap_account_grants_internal_role_via_me(client: AsyncClient) -> None:
    # The dev bootstrap builds an internal funder the Account-owns-Actor way: roles live on the
    # Account, and a linked dev actor inherits the principal. /me (dev-header path) surfaces the
    # nested account, so the internal role is visible exactly where the funding gate reads it.
    acct = await client.post(
        "/api/v1/accounts", json={"display_name": "Insider", "roles": ["internal"]}
    )
    assert acct.status_code == 201, acct.text
    assert acct.json()["roles"] == ["internal"]
    account_id = acct.json()["id"]

    actor = await client.post(
        "/api/v1/actors",
        json={"type": "human", "display_name": "Insider", "account_id": account_id},
    )
    assert actor.status_code == 201, actor.text
    assert actor.json()["account_id"] == account_id

    me = await client.get("/api/v1/me", headers={"X-Dev-Actor-Id": actor.json()["id"]})
    assert me.status_code == 200, me.text
    assert me.json()["account"]["roles"] == ["internal"]


async def test_one_human_actor_per_account_is_enforced(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    # Decision #7: a partial unique index (actors.account_id WHERE type='HUMAN') allows at most one
    # primary human Actor per Account; `agent` actors are unconstrained. The index is declared on
    # the model, so create_all (the test schema) installs it exactly as migration 0006 does.
    acct = await client.post("/api/v1/accounts", json={"display_name": "Org", "roles": []})
    assert acct.status_code == 201, acct.text
    account_id = UUID(acct.json()["id"])

    async with session_factory() as session:
        session.add(Actor(type=ActorType.HUMAN, display_name="First", account_id=account_id))
        await session.commit()

    # A second human on the same account violates the partial unique index.
    async with session_factory() as session:
        session.add(Actor(type=ActorType.HUMAN, display_name="Second", account_id=account_id))
        with pytest.raises(IntegrityError):
            await session.commit()

    # An `agent` actor on the same account is fine (the predicate is type='HUMAN').
    async with session_factory() as session:
        session.add(Actor(type=ActorType.AGENT, display_name="Agent", account_id=account_id))
        await session.commit()  # no error
