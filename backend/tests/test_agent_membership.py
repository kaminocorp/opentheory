"""0.54.0 — type-aware membership gate, roster ensure, OWNER-transfer hook.

DB-gated (skips without TEST_DATABASE_URL). Token mint / authorize token
swap / debit actor_id wiring / Crew UI / per-agent caps stay out.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.actor import Actor
from app.models.agent_session_token import AgentSessionToken
from app.models.checkpoint import Checkpoint
from app.models.enums import (
    ActorType,
    ProjectAgentRole,
    ProjectAgentStatus,
    ProjectRole,
)
from app.models.funding import FundingAllocation
from app.models.project_agent_member import ProjectAgentMember
from app.models.project_member import ProjectMember
from app.models.validation import Validation
from app.services.agent_actors import (
    AGENT_ACTOR_DISPLAY_NAME,
    get_or_create_project_agent_actor,
)
from app.services.agent_roster import get_roster_row, resume_project_agent
from app.services.agent_runs import start_agent_pass
from app.services.project_members import (
    ensure_can_manage,
    ensure_is_human_member,
    ensure_is_member,
)
from tests.principals import create_owned_project


def _headers(actor_id: str) -> dict[str, str]:
    return {"X-Dev-Actor-Id": actor_id}


async def _thread(client: AsyncClient, project_id: str, actor_id: str) -> str:
    resp = await client.post(
        f"/api/v1/projects/{project_id}/threads",
        json={"title": "T", "question": "q?"},
        headers=_headers(actor_id),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _add_admin(
    session_factory: async_sessionmaker,
    project_id: str,
    account_id: str,
    invited_by: str,
) -> None:
    async with session_factory() as session:
        session.add(
            ProjectMember(
                project_id=UUID(project_id),
                account_id=UUID(account_id),
                role=ProjectRole.ADMIN,
                invited_by_account_id=UUID(invited_by),
            )
        )
        await session.commit()


async def _insert_agent(
    session_factory: async_sessionmaker,
    *,
    project_id: str,
    display_name: str,
    account_id: str | None,
    roster: bool = False,
    status: ProjectAgentStatus = ProjectAgentStatus.ACTIVE,
    deployed_by: str | None = None,
    responsible: str | None = None,
    token: bool = False,
) -> tuple[str, str | None]:
    """Insert a named/crew agent. Returns ``(actor_id, token_id or None)``."""
    async with session_factory() as session:
        actor = Actor(
            type=ActorType.AGENT,
            display_name=display_name,
            account_id=UUID(account_id) if account_id else None,
            actor_metadata={"project_id": project_id},
        )
        session.add(actor)
        await session.flush()
        if roster:
            session.add(
                ProjectAgentMember(
                    project_id=UUID(project_id),
                    actor_id=actor.id,
                    deployed_by_account_id=UUID(deployed_by) if deployed_by else None,
                    responsible_account_id=UUID(responsible) if responsible else None,
                    role=ProjectAgentRole.RESEARCHER,
                    status=status,
                )
            )
        token_id = None
        if token:
            row = AgentSessionToken(
                project_id=UUID(project_id),
                actor_id=actor.id,
                minted_by_account_id=UUID(deployed_by) if deployed_by else None,
                token_hash=actor.id.bytes + b"tok",
                expires_at=datetime.now(UTC) + timedelta(days=30),
            )
            session.add(row)
            await session.flush()
            token_id = str(row.id)
        await session.commit()
        return str(actor.id), token_id


# --- get_or_create roster ensure ------------------------------------------------


async def test_get_or_create_on_owned_project_rosters_and_attaches_owner(
    client: AsyncClient, session_factory: async_sessionmaker, internal_funder
) -> None:
    owner_id, owner_account = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await create_owned_project(client, owner_id, "roster-ensure")

    async with session_factory() as session:
        actor = await get_or_create_project_agent_actor(session, UUID(project_id))
        await session.commit()
        assert actor.display_name == AGENT_ACTOR_DISPLAY_NAME
        assert str(actor.account_id) == owner_account
        row = await get_roster_row(session, UUID(project_id), actor.id)
        assert row is not None
        assert row.role == ProjectAgentRole.RESEARCHER
        assert row.status == ProjectAgentStatus.ACTIVE
        assert str(row.deployed_by_account_id) == owner_account
        assert str(row.responsible_account_id) == owner_account
        actor_id = actor.id

    async with session_factory() as session:
        again = await get_or_create_project_agent_actor(session, UUID(project_id))
        await session.commit()
        assert again.id == actor_id
        rows = (
            await session.execute(
                select(ProjectAgentMember).where(
                    ProjectAgentMember.project_id == UUID(project_id)
                )
            )
        ).scalars().all()
        assert len(rows) == 1


async def test_get_or_create_does_not_revive_suspended_roster(
    client: AsyncClient, session_factory: async_sessionmaker, internal_funder
) -> None:
    owner_id, owner_account = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await create_owned_project(client, owner_id, "roster-sticky")
    agent_id, _ = await _insert_agent(
        session_factory,
        project_id=project_id,
        display_name=AGENT_ACTOR_DISPLAY_NAME,
        account_id=owner_account,
        roster=True,
        status=ProjectAgentStatus.SUSPENDED,
        deployed_by=owner_account,
        responsible=owner_account,
    )

    async with session_factory() as session:
        actor = await get_or_create_project_agent_actor(session, UUID(project_id))
        await session.commit()
        assert str(actor.id) == agent_id
        row = await get_roster_row(session, UUID(project_id), actor.id)
        assert row is not None
        assert row.status == ProjectAgentStatus.SUSPENDED


# --- type-aware ensure_is_member --------------------------------------------


async def test_unrostered_and_inactive_agents_are_403(
    client: AsyncClient, session_factory: async_sessionmaker, internal_funder
) -> None:
    owner_id, owner_account = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await create_owned_project(client, owner_id, "gate-403")

    accountless, _ = await _insert_agent(
        session_factory,
        project_id=project_id,
        display_name=AGENT_ACTOR_DISPLAY_NAME,
        account_id=None,
    )
    owned_no_roster, _ = await _insert_agent(
        session_factory,
        project_id=project_id,
        display_name="Owned but unrostered",
        account_id=owner_account,
    )
    suspended, _ = await _insert_agent(
        session_factory,
        project_id=project_id,
        display_name="Suspended researcher",
        account_id=owner_account,
        roster=True,
        status=ProjectAgentStatus.SUSPENDED,
        deployed_by=owner_account,
        responsible=owner_account,
    )
    revoked, _ = await _insert_agent(
        session_factory,
        project_id=project_id,
        display_name="Revoked researcher",
        account_id=owner_account,
        roster=True,
        status=ProjectAgentStatus.REVOKED,
        deployed_by=owner_account,
        responsible=owner_account,
    )

    for agent_id in (accountless, owned_no_roster, suspended, revoked):
        resp = await client.post(
            f"/api/v1/projects/{project_id}/checkpoints",
            json={"summary": "should not land"},
            headers=_headers(agent_id),
        )
        assert resp.status_code == 403, (agent_id, resp.text)

    async with session_factory() as session:
        count = (
            await session.execute(
                select(Checkpoint).where(Checkpoint.project_id == UUID(project_id))
            )
        ).scalars().all()
        assert count == []


async def test_rostered_agent_may_write_research_not_fund_validate_or_manage(
    client: AsyncClient, session_factory: async_sessionmaker, internal_funder
) -> None:
    owner_id, owner_account = await internal_funder(
        client, roles=("internal",), display_name="Owner"
    )
    project_id = await create_owned_project(client, owner_id, "gate-write")
    thread_id = await _thread(client, project_id, owner_id)
    claim = await client.post(
        f"/api/v1/threads/{thread_id}/claims",
        json={"kind": "hypothesis", "statement": "X holds."},
        headers=_headers(owner_id),
    )
    assert claim.status_code == 201, claim.text
    claim_id = claim.json()["id"]

    agent_id, _ = await _insert_agent(
        session_factory,
        project_id=project_id,
        display_name="DeepSeek researcher",
        account_id=owner_account,
        roster=True,
        deployed_by=owner_account,
        responsible=owner_account,
    )

    note = await client.post(
        f"/api/v1/projects/{project_id}/checkpoints",
        json={"summary": "agent authored", "thread_id": thread_id},
        headers=_headers(agent_id),
    )
    assert note.status_code == 201, note.text
    assert note.json()["author_id"] == agent_id

    fund = await client.post(
        f"/api/v1/projects/{project_id}/funding",
        json={"amount": "1.00", "currency": "USD", "kind": "top_up", "source": "native"},
        headers=_headers(agent_id),
    )
    assert fund.status_code == 403, fund.text

    validation = await client.post(
        f"/api/v1/projects/{project_id}/validations",
        json={"target_type": "claim", "target_id": claim_id, "outcome": "passed"},
        headers=_headers(agent_id),
    )
    assert validation.status_code == 403, validation.text

    patch = await client.patch(
        f"/api/v1/projects/{project_id}",
        json={"title": "hijack"},
        headers=_headers(agent_id),
    )
    assert patch.status_code == 403, patch.text

    invite = await client.post(
        f"/api/v1/projects/{project_id}/invitations",
        json={"identifier": "@nobody"},
        headers=_headers(agent_id),
    )
    assert invite.status_code == 403, invite.text

    models = await client.put(
        f"/api/v1/projects/{project_id}/agent-models",
        json={"researcher": None},
        headers=_headers(agent_id),
    )
    assert models.status_code == 403, models.text

    async with session_factory() as session:
        assert (
            await session.execute(
                select(FundingAllocation).where(
                    FundingAllocation.project_id == UUID(project_id)
                )
            )
        ).scalars().all() == []
        assert (
            await session.execute(
                select(Validation).where(Validation.project_id == UUID(project_id))
            )
        ).scalars().all() == []


async def test_human_member_write_stays_human_no_sponsor(
    client: AsyncClient, internal_funder
) -> None:
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await create_owned_project(client, owner_id, "human-write")
    note = await client.post(
        f"/api/v1/projects/{project_id}/checkpoints",
        json={"summary": "human authored"},
        headers=_headers(owner_id),
    )
    assert note.status_code == 201, note.text
    body = note.json()
    assert body["author_id"] == owner_id
    assert body.get("sponsored_by_actor_id") in (None, )


async def test_system_actor_is_403(
    client: AsyncClient, session_factory: async_sessionmaker, internal_funder
) -> None:
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await create_owned_project(client, owner_id, "system-403")
    async with session_factory() as session:
        system = Actor(type=ActorType.SYSTEM, display_name="sys", account_id=None)
        session.add(system)
        await session.commit()
        system_id = system.id
        loaded = await session.get(Actor, system_id)
        assert loaded is not None
        with pytest.raises(HTTPException) as exc:
            await ensure_is_member(session, UUID(project_id), loaded)
        assert exc.value.status_code == 403
        with pytest.raises(HTTPException) as exc:
            await ensure_is_human_member(session, UUID(project_id), loaded)
        assert exc.value.status_code == 403
        with pytest.raises(HTTPException) as exc:
            await ensure_can_manage(session, UUID(project_id), loaded)
        assert exc.value.status_code == 403


# --- dark-loop commission gate ----------------------------------------------


async def test_start_agent_pass_without_roster_is_403(
    client: AsyncClient, session_factory: async_sessionmaker, internal_funder
) -> None:
    owner_id, owner_account = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await create_owned_project(client, owner_id, "loop-403")
    thread_id = await _thread(client, project_id, owner_id)
    await _insert_agent(
        session_factory,
        project_id=project_id,
        display_name=AGENT_ACTOR_DISPLAY_NAME,
        account_id=owner_account,
    )

    async with session_factory() as session:
        owner = await session.get(Actor, UUID(owner_id))
        assert owner is not None
        with pytest.raises(HTTPException) as exc:
            await start_agent_pass(
                session, UUID(project_id), UUID(thread_id), triggered_by=owner, role="researcher"
            )
        assert exc.value.status_code == 403


async def test_start_agent_pass_with_no_crew_yet_is_allowed(
    client: AsyncClient, session_factory: async_sessionmaker, internal_funder
) -> None:
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await create_owned_project(client, owner_id, "loop-lazy")
    thread_id = await _thread(client, project_id, owner_id)

    async with session_factory() as session:
        owner = await session.get(Actor, UUID(owner_id))
        assert owner is not None
        run = await start_agent_pass(
            session, UUID(project_id), UUID(thread_id), triggered_by=owner, role="researcher"
        )
        await session.commit()
        assert run.thread_id == UUID(thread_id)


# --- OWNER transfer ---------------------------------------------------------


async def test_owner_transfer_suspends_outgoing_and_crew_keeps_admin_deployed(
    client: AsyncClient, session_factory: async_sessionmaker, internal_funder
) -> None:
    owner_id, owner_account = await internal_funder(client, roles=(), display_name="Alice")
    admin_id, admin_account = await internal_funder(client, roles=(), display_name="Bob")
    project_id = await create_owned_project(client, owner_id, "xfer-roster")
    await _add_admin(session_factory, project_id, admin_account, owner_account)

    async with session_factory() as session:
        crew = await get_or_create_project_agent_actor(session, UUID(project_id))
        await session.commit()
        crew_id = str(crew.id)
        crew_account = str(crew.account_id)
        crew_roster = await get_roster_row(session, UUID(project_id), crew.id)
        assert crew_roster is not None
        crew_deployed = str(crew_roster.deployed_by_account_id)

    outgoing_named, outgoing_token = await _insert_agent(
        session_factory,
        project_id=project_id,
        display_name="Alice researcher",
        account_id=owner_account,
        roster=True,
        deployed_by=owner_account,
        responsible=owner_account,
        token=True,
    )
    admin_named, admin_token = await _insert_agent(
        session_factory,
        project_id=project_id,
        display_name="Bob researcher",
        account_id=admin_account,
        roster=True,
        deployed_by=admin_account,
        responsible=admin_account,
        token=True,
    )
    async with session_factory() as session:
        crew_tok = AgentSessionToken(
            project_id=UUID(project_id),
            actor_id=UUID(crew_id),
            minted_by_account_id=UUID(owner_account),
            token_hash=UUID(crew_id).bytes + b"crw",
            expires_at=datetime.now(UTC) + timedelta(days=30),
        )
        session.add(crew_tok)
        await session.commit()
        crew_token = str(crew_tok.id)

    xfer = await client.patch(
        f"/api/v1/projects/{project_id}/members/{admin_account}",
        json={"role": "owner"},
        headers=_headers(owner_id),
    )
    assert xfer.status_code == 200, xfer.text
    assert xfer.json()["role"] == "owner"

    async with session_factory() as session:
        crew_row = await get_roster_row(session, UUID(project_id), UUID(crew_id))
        out_row = await get_roster_row(session, UUID(project_id), UUID(outgoing_named))
        admin_row = await get_roster_row(session, UUID(project_id), UUID(admin_named))
        assert crew_row is not None and crew_row.status == ProjectAgentStatus.SUSPENDED
        assert out_row is not None and out_row.status == ProjectAgentStatus.SUSPENDED
        assert admin_row is not None and admin_row.status == ProjectAgentStatus.ACTIVE

        crew_actor = await session.get(Actor, UUID(crew_id))
        assert crew_actor is not None
        assert str(crew_actor.account_id) == crew_account
        assert str(crew_row.deployed_by_account_id) == crew_deployed
        assert str(out_row.deployed_by_account_id) == owner_account
        assert str(admin_row.deployed_by_account_id) == admin_account

        for token_id, expect_revoked in (
            (crew_token, True),
            (outgoing_token, True),
            (admin_token, False),
        ):
            token = await session.get(AgentSessionToken, UUID(token_id))
            assert token is not None
            assert (token.revoked_at is not None) is expect_revoked

        new_owner = await session.get(Actor, UUID(admin_id))
        assert new_owner is not None
        resumed = await resume_project_agent(
            session, UUID(project_id), UUID(crew_id), new_owner
        )
        await session.commit()
        assert resumed.status == ProjectAgentStatus.ACTIVE
        assert str(resumed.responsible_account_id) == admin_account
        assert str(resumed.deployed_by_account_id) == crew_deployed
        still = await session.get(AgentSessionToken, UUID(crew_token))
        assert still is not None
        assert still.revoked_at is not None

        crew_actor = await session.get(Actor, UUID(crew_id))
        assert str(crew_actor.account_id) == crew_account


# --- invitee-side human assertion -------------------------------------------


async def test_agent_cannot_accept_invitation_for_shared_account(
    client: AsyncClient, session_factory: async_sessionmaker, internal_funder
) -> None:
    owner = await internal_funder(client, roles=(), display_name="Owner")
    invitee_actor, invitee_account = await internal_funder(
        client, roles=(), display_name="Invitee"
    )
    owner_id, _ = owner
    project = await client.post(
        "/api/v1/projects",
        json={"title": "Inv", "slug": "agent-accept", "question": "q?"},
        headers=_headers(owner_id),
    )
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]

    me_resp = await client.get("/api/v1/me", headers=_headers(invitee_actor))
    assert me_resp.status_code == 200, me_resp.text
    identifier = f"@{me_resp.json()['account']['username']}"

    invited = await client.post(
        f"/api/v1/projects/{project_id}/invitations",
        json={"identifier": identifier},
        headers=_headers(owner_id),
    )
    assert invited.status_code == 201, invited.text
    invitation_id = invited.json()["id"]

    agent_id, _ = await _insert_agent(
        session_factory,
        project_id=project_id,
        display_name="Invitee agent",
        account_id=invitee_account,
        roster=True,
        deployed_by=invitee_account,
        responsible=invitee_account,
    )

    accept = await client.post(
        f"/api/v1/invitations/{invitation_id}/accept",
        headers=_headers(agent_id),
    )
    assert accept.status_code == 403, accept.text

    async with session_factory() as session:
        members = (
            await session.execute(
                select(ProjectMember).where(ProjectMember.project_id == UUID(project_id))
            )
        ).scalars().all()
        assert {str(m.account_id) for m in members} == {owner[1]}
