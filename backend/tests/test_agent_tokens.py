"""0.55.0 — OWNER agent-session mint / rotate / revoke, resolver, authorize swap.

DB-gated. Crew UI / per-agent caps stay out (spend stamp is 0.56.0).
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.deps import AGENT_SESSION_HTTP_DETAIL
from app.core.config import settings
from app.harness.auth import resolve_mcp_actor
from app.harness.live_mcp import invoke
from app.harness.session import REASON_ACTOR, REASON_NOT_MEMBER, HarnessSession, TurnRefused
from app.models.actor import Actor
from app.models.agent_session_token import AgentSessionToken
from app.models.checkpoint import Checkpoint
from app.models.contribution import Contribution
from app.models.enums import ActorType, ProjectAgentRole, ProjectAgentStatus, ProjectRole
from app.models.project_agent_member import ProjectAgentMember
from app.models.project_member import ProjectMember
from app.services.agent_actors import get_or_create_project_agent_actor
from app.services.agent_tokens import (
    TYP,
    encode_agent_session,
    hash_compact_jwt,
    looks_like_agent_session,
    resolve_agent_session_token,
)
from app.services.project_members import ensure_is_member
from tests.principals import create_owned_project

TEST_SECRET = "test-agent-session-secret-0.55.0-32b!!"


def _headers(actor_id: str) -> dict[str, str]:
    return {"X-Dev-Actor-Id": actor_id}


@pytest.fixture
def agent_secret(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "agent_session_jwt_secret", TEST_SECRET)
    monkeypatch.setattr(settings, "agent_session_max_ttl_seconds", 2_592_000)
    return TEST_SECRET


async def _roster_crew(
    session_factory: async_sessionmaker, project_id: str
) -> str:
    async with session_factory() as session:
        actor = await get_or_create_project_agent_actor(session, UUID(project_id))
        await session.commit()
        return str(actor.id)


async def _mint(
    client: AsyncClient,
    project_id: str,
    actor_id: str,
    owner_id: str,
    *,
    ttl_seconds: int | None = None,
) -> dict:
    body = {} if ttl_seconds is None else {"ttl_seconds": ttl_seconds}
    resp = await client.post(
        f"/api/v1/projects/{project_id}/agents/{actor_id}/tokens",
        json=body,
        headers=_headers(owner_id),
    )
    body = resp.json() if resp.content else {}
    return {"status": resp.status_code, "body": body, "text": resp.text}


# --- mint / rotate / revoke -------------------------------------------------


async def test_owner_mints_token_once_hashed(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    internal_funder,
    agent_secret,
) -> None:
    owner_id, owner_account = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await create_owned_project(client, owner_id, "mint-once")
    agent_id = await _roster_crew(session_factory, project_id)

    minted = await _mint(client, project_id, agent_id, owner_id)
    assert minted["status"] == 201, minted["text"]
    token = minted["body"]["token"]
    jti = minted["body"]["jti"]
    assert looks_like_agent_session(token)
    claims = jwt.decode(
        token,
        agent_secret,
        algorithms=["HS256"],
        audience="harness",
        issuer="opentheory",
    )
    assert claims["typ"] == TYP
    assert claims["sub"] == agent_id
    assert claims["proj"] == project_id
    assert claims["jti"] == jti
    assert claims["mby"] == owner_account
    assert claims["mba"] == owner_id
    exp = datetime.fromtimestamp(claims["exp"], UTC)
    iat = datetime.fromtimestamp(claims["iat"], UTC)
    assert timedelta(days=29) < (exp - iat) <= timedelta(days=30, seconds=2)

    async with session_factory() as session:
        row = await session.get(AgentSessionToken, UUID(jti))
        assert row is not None
        assert row.token_hash == hash_compact_jwt(token)
        assert row.revoked_at is None
        assert str(row.actor_id) == agent_id
        assert str(row.minted_by_actor_id) == owner_id


async def test_mint_shorter_ttl_and_rejects_over_max(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    internal_funder,
    agent_secret,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "agent_session_max_ttl_seconds", 3600)
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await create_owned_project(client, owner_id, "mint-ttl")
    agent_id = await _roster_crew(session_factory, project_id)

    short = await _mint(client, project_id, agent_id, owner_id, ttl_seconds=60)
    assert short["status"] == 201, short["text"]
    claims = jwt.decode(
        short["body"]["token"],
        agent_secret,
        algorithms=["HS256"],
        audience="harness",
        issuer="opentheory",
    )
    assert claims["exp"] - claims["iat"] == 60

    over = await _mint(client, project_id, agent_id, owner_id, ttl_seconds=3601)
    assert over["status"] == 422
    assert "OPENTHEORY_AGENT_SESSION_MAX_TTL_SECONDS" in over["body"]["detail"]


async def test_mint_fails_closed_without_secret(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    internal_funder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "agent_session_jwt_secret", None)
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await create_owned_project(client, owner_id, "mint-no-secret")
    agent_id = await _roster_crew(session_factory, project_id)
    minted = await _mint(client, project_id, agent_id, owner_id)
    assert minted["status"] == 503
    assert "signing key" in minted["body"]["detail"].lower()


async def test_mint_forbidden_for_admin_agent_and_outsider(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    internal_funder,
    agent_secret,
) -> None:
    owner_id, owner_account = await internal_funder(client, roles=(), display_name="Owner")
    admin_id, admin_account = await internal_funder(client, roles=(), display_name="Admin")
    outsider_id, _ = await internal_funder(client, roles=(), display_name="Eve")
    project_id = await create_owned_project(client, owner_id, "mint-who")
    agent_id = await _roster_crew(session_factory, project_id)
    async with session_factory() as session:
        session.add(
            ProjectMember(
                project_id=UUID(project_id),
                account_id=UUID(admin_account),
                role=ProjectRole.ADMIN,
                invited_by_account_id=UUID(owner_account),
            )
        )
        await session.commit()

    assert (await _mint(client, project_id, agent_id, admin_id))["status"] == 403
    assert (await _mint(client, project_id, agent_id, outsider_id))["status"] == 403
    # Agent cannot mint for itself (no self-renew).
    agent_mint = await client.post(
        f"/api/v1/projects/{project_id}/agents/{agent_id}/tokens",
        json={},
        headers=_headers(agent_id),
    )
    assert agent_mint.status_code == 403


async def test_mint_requires_active_roster(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    internal_funder,
    agent_secret,
) -> None:
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await create_owned_project(client, owner_id, "mint-inactive")
    agent_id = await _roster_crew(session_factory, project_id)
    async with session_factory() as session:
        from app.services.agent_roster import get_roster_row

        row = await get_roster_row(session, UUID(project_id), UUID(agent_id))
        assert row is not None
        row.status = ProjectAgentStatus.SUSPENDED
        session.add(row)
        await session.commit()
    minted = await _mint(client, project_id, agent_id, owner_id)
    assert minted["status"] == 403


async def test_rotate_revokes_old_and_old_jwt_fails_authorize(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    internal_funder,
    agent_secret,
) -> None:
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await create_owned_project(client, owner_id, "rotate")
    agent_id = await _roster_crew(session_factory, project_id)
    first = await _mint(client, project_id, agent_id, owner_id)
    assert first["status"] == 201
    old_token = first["body"]["token"]
    old_jti = first["body"]["jti"]

    rotated = await client.post(
        f"/api/v1/projects/{project_id}/agents/{agent_id}/tokens/{old_jti}/rotate",
        json={},
        headers=_headers(owner_id),
    )
    assert rotated.status_code == 201, rotated.text
    new_body = rotated.json()
    assert new_body["jti"] != old_jti
    assert new_body["token"] != old_token

    async with session_factory() as session:
        old = await session.get(AgentSessionToken, UUID(old_jti))
        assert old is not None
        assert old.revoked_at is not None
        with pytest.raises(HTTPException) as exc:
            await resolve_agent_session_token(session, old_token)
        assert exc.value.status_code == 401
        fresh = await resolve_agent_session_token(session, new_body["token"])
        assert str(fresh.id) == agent_id
        assert fresh.type == ActorType.AGENT

    session = HarnessSession(
        project_id=project_id,
        session_factory=session_factory,
        actor_env={"OPENTHEORY_ACTOR_JWT": old_token},
    )
    try:
        await session.authorize()
        raise AssertionError("rotated token must refuse authorize")
    except TurnRefused as refused:
        assert refused.reason == REASON_ACTOR


async def test_revoke_takes_effect_on_next_resolve(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    internal_funder,
    agent_secret,
) -> None:
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await create_owned_project(client, owner_id, "revoke")
    agent_id = await _roster_crew(session_factory, project_id)
    minted = await _mint(client, project_id, agent_id, owner_id)
    token = minted["body"]["token"]
    jti = minted["body"]["jti"]
    revoked = await client.post(
        f"/api/v1/projects/{project_id}/agents/{agent_id}/tokens/{jti}/revoke",
        headers=_headers(owner_id),
    )
    assert revoked.status_code == 204, revoked.text
    async with session_factory() as session:
        with pytest.raises(HTTPException) as exc:
            await resolve_agent_session_token(session, token)
        assert exc.value.status_code == 401


# --- resolver ---------------------------------------------------------------


async def test_resolver_stamps_last_used_and_never_returns_human(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    internal_funder,
    agent_secret,
) -> None:
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await create_owned_project(client, owner_id, "resolve")
    agent_id = await _roster_crew(session_factory, project_id)
    minted = await _mint(client, project_id, agent_id, owner_id)
    token = minted["body"]["token"]
    jti = minted["body"]["jti"]

    async with session_factory() as session:
        actor = await resolve_mcp_actor(session, {"OPENTHEORY_ACTOR_JWT": token})
        assert actor.type == ActorType.AGENT
        assert str(actor.id) == agent_id
        await session.commit()
        row = await session.get(AgentSessionToken, UUID(jti))
        assert row is not None
        assert row.last_used_at is not None

    # A token that only looks like agent_session (wrong key) is 401, not a human.
    forged = jwt.encode(
        {
            "iss": "opentheory",
            "aud": "harness",
            "typ": TYP,
            "sub": agent_id,
            "proj": project_id,
            "jti": str(uuid4()),
            "mby": str(uuid4()),
            "mba": owner_id,
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(days=1),
        },
        "other-secret-not-the-real-one!!!",
        algorithm="HS256",
        headers={"typ": TYP},
    )
    async with session_factory() as session:
        with pytest.raises(HTTPException) as exc:
            await resolve_mcp_actor(session, {"OPENTHEORY_ACTOR_JWT": forged})
        assert exc.value.status_code == 401


async def test_resolver_fails_closed_when_secret_missing(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    internal_funder,
    agent_secret,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await create_owned_project(client, owner_id, "resolve-no-secret")
    agent_id = await _roster_crew(session_factory, project_id)
    minted = await _mint(client, project_id, agent_id, owner_id)
    monkeypatch.setattr(settings, "agent_session_jwt_secret", None)
    async with session_factory() as session:
        with pytest.raises(HTTPException) as exc:
            await resolve_agent_session_token(session, minted["body"]["token"])
        assert exc.value.status_code == 401


async def test_resolver_refuses_expired_and_hash_mismatch(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    internal_funder,
    agent_secret,
) -> None:
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await create_owned_project(client, owner_id, "resolve-bad")
    agent_id = await _roster_crew(session_factory, project_id)
    minted = await _mint(client, project_id, agent_id, owner_id, ttl_seconds=60)
    token = minted["body"]["token"]
    jti = minted["body"]["jti"]

    async with session_factory() as session:
        row = await session.get(AgentSessionToken, UUID(jti))
        assert row is not None
        row.expires_at = datetime.now(UTC) - timedelta(seconds=5)
        session.add(row)
        await session.commit()
        with pytest.raises(HTTPException) as exc:
            await resolve_agent_session_token(session, token)
        assert exc.value.status_code == 401

    minted2 = await _mint(client, project_id, agent_id, owner_id)
    async with session_factory() as session:
        row = await session.get(AgentSessionToken, UUID(minted2["body"]["jti"]))
        assert row is not None
        row.token_hash = b"\x00" * 32
        session.add(row)
        await session.commit()
        with pytest.raises(HTTPException) as exc:
            await resolve_agent_session_token(session, minted2["body"]["token"])
        assert exc.value.status_code == 401


# --- MCP write attribution + authorize swap --------------------------------


async def test_agent_token_checkpoint_authors_agent_and_snapshots_sponsor(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    internal_funder,
    agent_secret,
) -> None:
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await create_owned_project(client, owner_id, "mcp-sponsor")
    agent_id = await _roster_crew(session_factory, project_id)
    minted = await _mint(client, project_id, agent_id, owner_id)
    result = await invoke(
        "create_checkpoint",
        {"project_id": project_id, "summary": "agent note"},
        session_factory=session_factory,
        env={"OPENTHEORY_ACTOR_JWT": minted["body"]["token"]},
    )
    assert result["minted"] is True, result
    async with session_factory() as session:
        checkpoint = await session.get(Checkpoint, UUID(result["checkpoint_id"]))
        assert checkpoint is not None
        assert str(checkpoint.author_id) == agent_id
        assert str(checkpoint.sponsored_by_actor_id) == owner_id
        contrib = (
            await session.execute(
                select(Contribution).where(Contribution.checkpoint_id == checkpoint.id)
            )
        ).scalar_one()
        assert str(contrib.actor_id) == agent_id


async def test_human_checkpoint_has_no_sponsor(
    client: AsyncClient, session_factory: async_sessionmaker, internal_funder
) -> None:
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await create_owned_project(client, owner_id, "human-nosponsor")
    thread = await client.post(
        f"/api/v1/projects/{project_id}/threads",
        json={"title": "T", "question": "q?"},
        headers=_headers(owner_id),
    )
    assert thread.status_code == 201
    note = await client.post(
        f"/api/v1/projects/{project_id}/checkpoints",
        json={"summary": "human note", "thread_id": thread.json()["id"]},
        headers=_headers(owner_id),
    )
    assert note.status_code == 201, note.text
    body = note.json()
    assert body["author_id"] == owner_id
    assert body.get("sponsored_by_actor_id") is None


async def test_agent_token_authorize_and_cross_project_refuse(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    internal_funder,
    agent_secret,
) -> None:
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    project_a = await create_owned_project(client, owner_id, "auth-a")
    project_b = await create_owned_project(client, owner_id, "auth-b")
    agent_a = await _roster_crew(session_factory, project_a)
    minted = await _mint(client, project_a, agent_a, owner_id)
    token = minted["body"]["token"]

    ok = HarnessSession(
        project_id=project_a,
        session_factory=session_factory,
        actor_env={"OPENTHEORY_ACTOR_JWT": token},
    )
    hold = await ok.authorize()
    assert hold is not None

    other = HarnessSession(
        project_id=project_b,
        session_factory=session_factory,
        actor_env={"OPENTHEORY_ACTOR_JWT": token},
    )
    try:
        await other.authorize()
        raise AssertionError("token for A must not authorize on B")
    except TurnRefused as refused:
        assert refused.reason == REASON_NOT_MEMBER


async def test_agent_token_is_403_on_http_routes(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    internal_funder,
    agent_secret,
) -> None:
    owner_id, _ = await internal_funder(client, roles=("internal",), display_name="Owner")
    project_id = await create_owned_project(client, owner_id, "http-refuse")
    agent_id = await _roster_crew(session_factory, project_id)
    minted = await _mint(client, project_id, agent_id, owner_id)
    bearer = {"Authorization": f"Bearer {minted['body']['token']}"}

    reads_and_writes = [
        await client.get("/api/v1/me", headers=bearer),
        await client.get("/api/v1/me/invitations", headers=bearer),
        await client.get(f"/api/v1/projects/{project_id}/agents", headers=bearer),
        await client.post(
            f"/api/v1/projects/{project_id}/agents",
            json={"display_name": "Rogue"},
            headers=bearer,
        ),
        await client.patch(
            f"/api/v1/projects/{project_id}/agents/{agent_id}",
            json={"status": "suspended"},
            headers=bearer,
        ),
        await client.post(
            f"/api/v1/projects/{project_id}/threads",
            json={"title": "T", "question": "q?"},
            headers=bearer,
        ),
        await client.post(
            f"/api/v1/projects/{project_id}/checkpoints",
            json={"summary": "http agent note"},
            headers=bearer,
        ),
        await client.post(
            f"/api/v1/projects/{project_id}/instruments/calc.eval/run",
            json={"inputs": {"expression": "1+1"}},
            headers=bearer,
        ),
        await client.post(
            f"/api/v1/projects/{project_id}/funding",
            json={"amount": "1.00", "currency": "USD", "kind": "top_up", "source": "native"},
            headers=bearer,
        ),
    ]
    for resp in reads_and_writes:
        assert resp.status_code == 403, resp.text
        assert resp.json()["detail"] == AGENT_SESSION_HTTP_DETAIL

    thread = await client.post(
        f"/api/v1/projects/{project_id}/threads",
        json={"title": "T", "question": "q?"},
        headers=_headers(owner_id),
    )
    assert thread.status_code == 201, thread.text
    claim = await client.post(
        f"/api/v1/threads/{thread.json()['id']}/claims",
        json={"kind": "hypothesis", "statement": "s"},
        headers=bearer,
    )
    assert claim.status_code == 403, claim.text
    assert claim.json()["detail"] == AGENT_SESSION_HTTP_DETAIL

    # MCP path still works end-to-end (author = agent, sponsor = owner).
    mcp = await invoke(
        "create_checkpoint",
        {"project_id": project_id, "summary": "mcp after http refuse"},
        session_factory=session_factory,
        env={"OPENTHEORY_ACTOR_JWT": minted["body"]["token"]},
    )
    assert mcp["minted"] is True, mcp
    async with session_factory() as session:
        checkpoint = await session.get(Checkpoint, UUID(mcp["checkpoint_id"]))
        assert checkpoint is not None
        assert str(checkpoint.author_id) == agent_id
        assert str(checkpoint.sponsored_by_actor_id) == owner_id


async def test_token_for_a_refuses_mcp_write_on_b_even_when_rostered_on_both(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    internal_funder,
    agent_secret,
) -> None:
    owner_id, owner_account = await internal_funder(client, roles=(), display_name="Owner")
    project_a = await create_owned_project(client, owner_id, "dual-a")
    project_b = await create_owned_project(client, owner_id, "dual-b")
    agent_id = await _roster_crew(session_factory, project_a)
    async with session_factory() as session:
        session.add(
            ProjectAgentMember(
                project_id=UUID(project_b),
                actor_id=UUID(agent_id),
                deployed_by_account_id=UUID(owner_account),
                responsible_account_id=UUID(owner_account),
                role=ProjectAgentRole.RESEARCHER,
                status=ProjectAgentStatus.ACTIVE,
            )
        )
        await session.commit()
    minted = await _mint(client, project_a, agent_id, owner_id)
    result = await invoke(
        "create_checkpoint",
        {"project_id": project_b, "summary": "cross project"},
        session_factory=session_factory,
        env={"OPENTHEORY_ACTOR_JWT": minted["body"]["token"]},
    )
    assert result["minted"] is False, result
    assert result.get("status_code") == 403


async def test_resolver_rejects_future_iat(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    internal_funder,
    agent_secret,
) -> None:
    owner_id, owner_account = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await create_owned_project(client, owner_id, "future-iat")
    agent_id = await _roster_crew(session_factory, project_id)
    now = datetime.now(UTC)
    jti = uuid4()
    compact = encode_agent_session(
        jti=jti,
        actor_id=UUID(agent_id),
        project_id=UUID(project_id),
        minted_by_account_id=UUID(owner_account),
        minted_by_actor_id=UUID(owner_id),
        expires_at=now + timedelta(days=1),
        issued_at=now + timedelta(hours=1),
        secret=agent_secret,
    )
    async with session_factory() as session:
        session.add(
            AgentSessionToken(
                id=jti,
                project_id=UUID(project_id),
                actor_id=UUID(agent_id),
                minted_by_account_id=UUID(owner_account),
                minted_by_actor_id=UUID(owner_id),
                token_hash=hash_compact_jwt(compact),
                expires_at=now + timedelta(days=1),
            )
        )
        await session.commit()
        with pytest.raises(HTTPException) as exc:
            await resolve_agent_session_token(session, compact)
        assert exc.value.status_code == 401


async def test_agent_jwt_file_alias_resolves(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    internal_funder,
    agent_secret,
    tmp_path,
) -> None:
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await create_owned_project(client, owner_id, "jwt-file")
    agent_id = await _roster_crew(session_factory, project_id)
    minted = await _mint(client, project_id, agent_id, owner_id)
    path = tmp_path / "agent.jwt"
    path.write_text(minted["body"]["token"], encoding="utf-8")
    async with session_factory() as session:
        actor = await resolve_mcp_actor(
            session, {"OPENTHEORY_AGENT_JWT_FILE": str(path)}
        )
        assert str(actor.id) == agent_id
        assert actor.type == ActorType.AGENT


async def test_rostered_agent_dev_id_still_authorizes(
    client: AsyncClient, session_factory: async_sessionmaker, internal_funder
) -> None:
    """Flagged DEV_ACTOR_ID of a rostered agent still passes authorize (0.54.0 pin)."""
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await create_owned_project(client, owner_id, "dev-agent-auth")
    agent_id = await _roster_crew(session_factory, project_id)
    async with session_factory() as session:
        actor = await session.get(Actor, UUID(agent_id))
        assert actor is not None
        await ensure_is_member(session, UUID(project_id), actor)
    hold = await HarnessSession(
        project_id=project_id,
        session_factory=session_factory,
        actor_env={"OPENTHEORY_DEV_ACTOR_ID": agent_id},
    ).authorize()
    assert hold is not None
