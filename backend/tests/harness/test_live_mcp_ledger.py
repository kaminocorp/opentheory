"""DB-backed live MCP door — membership, chokepoint, mint-nothing.

Skips without TEST_DATABASE_URL (same gate as the rest of the ledger suite).
"""

from __future__ import annotations

import time
from decimal import Decimal
from uuid import UUID

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import settings
from app.harness.auth import JWT_FILE_ENV, resolve_mcp_actor
from app.harness.live_mcp import invoke
from app.models.checkpoint import Checkpoint
from app.models.compute_debit import ComputeDebit
from app.models.contribution import Contribution
from app.models.enums import ComputeDebitKind, ComputeDebitRateSource
from app.services.compute import BUDGET_EXHAUSTED
from tests.principals import create_owned_project, make_dev_principal

_SIGNING_KEY = ec.generate_private_key(ec.SECP256R1())
_PUBLIC_KEY = _SIGNING_KEY.public_key()
_OTHER_KEY = ec.generate_private_key(ec.SECP256R1())


@pytest.fixture
def auth_settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "supabase_jwt_audience", "authenticated")
    monkeypatch.setattr("app.core.auth._signing_key", lambda _token: _PUBLIC_KEY)
    return settings


def _mint(
    sub: str,
    *,
    key: ec.EllipticCurvePrivateKey = _SIGNING_KEY,
    email: str | None = None,
    name: str | None = None,
    exp_delta: int = 3600,
) -> str:
    now = int(time.time())
    payload: dict = {
        "sub": sub,
        "aud": "authenticated",
        "iat": now,
        "exp": now + exp_delta,
    }
    if email is not None:
        payload["email"] = email
    if name is not None:
        payload["user_metadata"] = {"name": name}
    return jwt.encode(payload, key, algorithm="ES256", headers={"kid": "test-key"})


async def _checkpoint_count(session_factory: async_sessionmaker, project_id: str) -> int:
    async with session_factory() as session:
        result = await session.execute(
            select(func.count())
            .select_from(Checkpoint)
            .where(Checkpoint.project_id == UUID(project_id))
        )
        return int(result.scalar_one())


async def _thread(client: AsyncClient, project_id: str, actor_id: str) -> str:
    resp = await client.post(
        f"/api/v1/projects/{project_id}/threads",
        json={"title": "Decompose", "question": "What is 1+1?"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _claim(client: AsyncClient, thread_id: str, actor_id: str) -> str:
    resp = await client.post(
        f"/api/v1/threads/{thread_id}/claims",
        json={"kind": "hypothesis", "statement": "1 + 1 equals 2."},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_member_dev_actor_runs_calc_eval_through_chokepoint(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await make_dev_principal(client, display_name="Ada")
    project_id = await create_owned_project(client, actor_id, "live-mcp-calc")
    before = await _checkpoint_count(session_factory, project_id)

    result = await invoke(
        "run_instrument",
        {
            "project_id": project_id,
            "name": "calc.eval",
            "input": {"expression": "1 + 1"},
        },
        session_factory=session_factory,
        env={"OPENTHEORY_DEV_ACTOR_ID": actor_id},
    )

    assert result["ok"] is True
    assert result["stub"] is False
    assert result["minted"] is True
    assert result["status"] == "result"
    assert result["instrument"] == "calc.eval"
    assert result["checkpoint_id"]
    assert await _checkpoint_count(session_factory, project_id) == before + 1

    async with session_factory() as session:
        contrib = (
            await session.execute(
                select(Contribution).where(
                    Contribution.checkpoint_id == UUID(result["checkpoint_id"])
                )
            )
        ).scalar_one()
        assert contrib.action == "tool_run"
        assert str(contrib.actor_id) == actor_id


async def test_member_can_create_checkpoint_through_chokepoint(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await make_dev_principal(client, display_name="Ada")
    project_id = await create_owned_project(client, actor_id, "live-mcp-note")
    before = await _checkpoint_count(session_factory, project_id)

    result = await invoke(
        "create_checkpoint",
        {"project_id": project_id, "summary": "Note from the live door"},
        session_factory=session_factory,
        env={"OPENTHEORY_DEV_ACTOR_ID": actor_id},
    )

    assert result["ok"] is True
    assert result["minted"] is True
    assert result["contribution_kind"] == "create_checkpoint"
    assert await _checkpoint_count(session_factory, project_id) == before + 1


async def test_non_member_cannot_write(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    owner_id = await make_dev_principal(client, display_name="Owner")
    outsider_id = await make_dev_principal(client, display_name="Eve")
    project_id = await create_owned_project(client, owner_id, "live-mcp-outsider")
    before = await _checkpoint_count(session_factory, project_id)

    run = await invoke(
        "run_instrument",
        {
            "project_id": project_id,
            "name": "calc.eval",
            "input": {"expression": "2 + 2"},
        },
        session_factory=session_factory,
        env={"OPENTHEORY_DEV_ACTOR_ID": outsider_id},
    )
    note = await invoke(
        "create_checkpoint",
        {"project_id": project_id, "summary": "should not land"},
        session_factory=session_factory,
        env={"OPENTHEORY_DEV_ACTOR_ID": outsider_id},
    )

    assert run["ok"] is False
    assert run["minted"] is False
    assert run["status_code"] == 403
    assert note["ok"] is False
    assert note["minted"] is False
    assert note["status_code"] == 403
    assert await _checkpoint_count(session_factory, project_id) == before


async def test_instrument_failure_mints_nothing(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await make_dev_principal(client, display_name="Ada")
    project_id = await create_owned_project(client, actor_id, "live-mcp-fail")
    before = await _checkpoint_count(session_factory, project_id)

    result = await invoke(
        "run_instrument",
        {
            "project_id": project_id,
            "name": "calc.eval",
            "input": {"expression": "this is not even math !!!"},
        },
        session_factory=session_factory,
        env={"OPENTHEORY_DEV_ACTOR_ID": actor_id},
    )

    assert result["ok"] is False
    assert result["minted"] is False
    assert result["checkpoint_id"] is None
    assert result["status_code"] == 422
    assert await _checkpoint_count(session_factory, project_id) == before


async def test_unknown_instrument_mints_nothing(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await make_dev_principal(client, display_name="Ada")
    project_id = await create_owned_project(client, actor_id, "live-mcp-unknown")
    before = await _checkpoint_count(session_factory, project_id)

    result = await invoke(
        "run_instrument",
        {"project_id": project_id, "name": "not.a.real.instrument", "input": {}},
        session_factory=session_factory,
        env={"OPENTHEORY_DEV_ACTOR_ID": actor_id},
    )

    assert result["ok"] is False
    assert result["minted"] is False
    assert result["status_code"] == 404
    assert await _checkpoint_count(session_factory, project_id) == before


async def test_missing_credential_is_401(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await make_dev_principal(client, display_name="Ada")
    project_id = await create_owned_project(client, actor_id, "live-mcp-unauth")
    before = await _checkpoint_count(session_factory, project_id)

    result = await invoke(
        "run_instrument",
        {
            "project_id": project_id,
            "name": "calc.eval",
            "input": {"expression": "1"},
        },
        session_factory=session_factory,
        env={},
    )

    assert result["ok"] is False
    assert result["minted"] is False
    assert result["status_code"] == 401
    assert await _checkpoint_count(session_factory, project_id) == before


async def test_jwt_file_member_can_write(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    auth_settings,
    tmp_path,
) -> None:
    token = _mint("idp-mcp-member", email="mcp@example.com", name="MCP Ada")
    token_path = tmp_path / "actor.jwt"
    token_path.write_text(token, encoding="utf-8")

    me = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200, me.text
    actor_id = me.json()["id"]
    project = await client.post(
        "/api/v1/projects",
        json={"title": "JWT project", "slug": "live-mcp-jwt", "question": "q?"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]
    before = await _checkpoint_count(session_factory, project_id)

    result = await invoke(
        "run_instrument",
        {
            "project_id": project_id,
            "name": "calc.eval",
            "input": {"expression": "3 + 4"},
        },
        session_factory=session_factory,
        env={JWT_FILE_ENV: str(token_path)},
    )

    assert result["ok"] is True
    assert result["minted"] is True
    assert result["status"] == "result"
    assert await _checkpoint_count(session_factory, project_id) == before + 1

    async with session_factory() as session:
        actor = await resolve_mcp_actor(session, {JWT_FILE_ENV: str(token_path)})
        assert str(actor.id) == actor_id


async def test_bad_jwt_cannot_write(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    auth_settings,
    tmp_path,
) -> None:
    good = _mint("idp-mcp-owner", email="owner@example.com", name="Owner")
    me = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {good}"})
    assert me.status_code == 200, me.text
    project = await client.post(
        "/api/v1/projects",
        json={"title": "JWT lock", "slug": "live-mcp-bad-jwt", "question": "q?"},
        headers={"Authorization": f"Bearer {good}"},
    )
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]
    before = await _checkpoint_count(session_factory, project_id)

    forged = _mint("idp-mcp-forged", key=_OTHER_KEY, email="eve@example.com")
    token_path = tmp_path / "forged.jwt"
    token_path.write_text(forged, encoding="utf-8")

    result = await invoke(
        "create_checkpoint",
        {"project_id": project_id, "summary": "forged write"},
        session_factory=session_factory,
        env={JWT_FILE_ENV: str(token_path)},
    )

    assert result["ok"] is False
    assert result["minted"] is False
    assert result["status_code"] == 401
    assert await _checkpoint_count(session_factory, project_id) == before


async def test_reads_require_membership_and_mint_nothing(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    owner_id = await make_dev_principal(client, display_name="Owner")
    outsider_id = await make_dev_principal(client, display_name="Eve")
    project_id = await create_owned_project(client, owner_id, "live-mcp-reads")
    thread_id = await _thread(client, project_id, owner_id)
    await _claim(client, thread_id, owner_id)
    before = await _checkpoint_count(session_factory, project_id)

    claims = await invoke(
        "list_claims",
        {"project_id": project_id},
        session_factory=session_factory,
        env={"OPENTHEORY_DEV_ACTOR_ID": owner_id},
    )
    context = await invoke(
        "get_thread_context",
        {"thread_id": thread_id},
        session_factory=session_factory,
        env={"OPENTHEORY_DEV_ACTOR_ID": owner_id},
    )
    budget = await invoke(
        "get_budget",
        {"project_id": project_id},
        session_factory=session_factory,
        env={"OPENTHEORY_DEV_ACTOR_ID": owner_id},
    )
    forbidden = await invoke(
        "list_claims",
        {"project_id": project_id},
        session_factory=session_factory,
        env={"OPENTHEORY_DEV_ACTOR_ID": outsider_id},
    )

    assert claims["ok"] is True
    assert len(claims["claims"]) == 1
    assert claims["claims"][0]["statement"] == "1 + 1 equals 2."
    assert context["ok"] is True
    assert len(context["open_claims"]) == 1
    assert "to_raise" in context["open_claims"][0]
    assert budget["ok"] is True
    assert budget["available"] is not None
    assert forbidden["ok"] is False
    assert forbidden["status_code"] == 403
    assert await _checkpoint_count(session_factory, project_id) == before


async def test_exhausted_budget_refuses_write(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await make_dev_principal(
        client, display_name="Funder", roles=("internal",)
    )
    project_id = await create_owned_project(client, actor_id, "live-mcp-budget")
    funded = await client.post(
        f"/api/v1/projects/{project_id}/funding",
        json={"amount": "10.00", "currency": "USD", "kind": "top_up", "source": "native"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert funded.status_code == 201, funded.text

    async with session_factory() as session:
        session.add(
            ComputeDebit(
                project_id=UUID(project_id),
                tokens_used=1_000,
                amount=Decimal("10"),
                currency="USD",
                rate_per_1k=Decimal("10"),
                rate_source=ComputeDebitRateSource.BLENDED_FALLBACK,
                kind=ComputeDebitKind.PLANNING,
            )
        )
        await session.commit()

    before = await _checkpoint_count(session_factory, project_id)
    result = await invoke(
        "run_instrument",
        {
            "project_id": project_id,
            "name": "calc.eval",
            "input": {"expression": "1 + 1"},
        },
        session_factory=session_factory,
        env={"OPENTHEORY_DEV_ACTOR_ID": actor_id},
    )

    assert result["ok"] is False
    assert result["minted"] is False
    assert result["error"] == BUDGET_EXHAUSTED
    assert await _checkpoint_count(session_factory, project_id) == before
