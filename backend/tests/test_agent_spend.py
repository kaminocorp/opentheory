"""0.56.0 — ComputeDebit.actor_id on harness spend and the built-in pass.

DB-gated. Crew UI / ops actor_* / per-agent cap enforcement stay out.
"""

from decimal import Decimal
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agent.planner import PlannedRun, PlanResult
from app.core.config import settings
from app.harness.session import (
    REASON_ACTOR,
    REASON_CREDENTIAL_DIVERGENCE,
    SESSION_NOTES,
    HarnessSession,
    TurnRefused,
    is_daily_cap_adjustment,
    load_today_adjustments,
)
from app.models.actor import Actor
from app.models.agent_run import AgentRun
from app.models.compute_debit import ComputeDebit
from app.models.enums import (
    ActorType,
    AgentRunStatus,
    ComputeDebitKind,
    FundingKind,
    FundingSource,
    FundingStatus,
)
from app.models.funding import FundingAllocation
from app.models.project import Project
from app.services.agent_actors import get_or_create_project_agent_actor
from app.services.agent_runs import run_agent_pass
from tests.principals import create_owned_project

TEST_SECRET = "test-agent-session-secret-0.56.0-32b!!"


def _headers(actor_id: str) -> dict[str, str]:
    return {"X-Dev-Actor-Id": actor_id}


@pytest.fixture
def agent_secret(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "agent_session_jwt_secret", TEST_SECRET)
    monkeypatch.setattr(settings, "agent_session_max_ttl_seconds", 2_592_000)
    return TEST_SECRET


async def _roster_crew(session_factory: async_sessionmaker, project_id: str) -> str:
    async with session_factory() as session:
        actor = await get_or_create_project_agent_actor(session, UUID(project_id))
        await session.commit()
        return str(actor.id)


async def _mint(
    client: AsyncClient, project_id: str, actor_id: str, owner_id: str
) -> dict:
    resp = await client.post(
        f"/api/v1/projects/{project_id}/agents/{actor_id}/tokens",
        json={},
        headers=_headers(owner_id),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _debit_rows(session_factory: async_sessionmaker, project_id: str) -> list[ComputeDebit]:
    async with session_factory() as session:
        result = await session.execute(
            select(ComputeDebit).where(ComputeDebit.project_id == UUID(project_id))
        )
        return [
            row
            for row in result.scalars().all()
            if row.tokens_used > 0 and not is_daily_cap_adjustment(row.notes)
        ]


async def _adjustments(session_factory: async_sessionmaker, project_id: str):
    async with session_factory() as session:
        return await load_today_adjustments(session, UUID(project_id))


async def test_agent_token_spend_and_hold_stamp_the_agent(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    internal_funder,
    agent_secret,
) -> None:
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await create_owned_project(client, owner_id, "spend-agent")
    agent_id = await _roster_crew(session_factory, project_id)
    minted = await _mint(client, project_id, agent_id, owner_id)

    session = HarnessSession(
        project_id=project_id,
        session_factory=session_factory,
        env={"OPENTHEORY_ACTOR_JWT": minted["token"]},
    )
    hold = await session.authorize()
    assert hold is not None
    holds = await _adjustments(session_factory, project_id)
    assert len(holds) == 1
    assert holds[0].amount == 0
    assert SESSION_NOTES in (holds[0].notes or "")
    assert str(holds[0].actor_id) == agent_id

    spent = await session.record_spend(
        tokens_used=20,
        model="test-model",
        prompt_tokens=15,
        completion_tokens=5,
        hold=hold,
    )
    assert spent is True
    debits = await _debit_rows(session_factory, project_id)
    assert len(debits) == 1
    assert str(debits[0].actor_id) == agent_id
    assert debits[0].kind is ComputeDebitKind.PLANNING
    assert SESSION_NOTES in (debits[0].notes or "")

    rows = await _adjustments(session_factory, project_id)
    assert all(str(row.actor_id) == agent_id for row in rows)
    assert all(row.amount == 0 for row in rows)


async def test_revoked_mid_turn_still_bills_then_next_authorize_refuses(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    internal_funder,
    agent_secret,
) -> None:
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await create_owned_project(client, owner_id, "spend-revoke")
    agent_id = await _roster_crew(session_factory, project_id)
    minted = await _mint(client, project_id, agent_id, owner_id)
    token = minted["token"]
    jti = minted["jti"]

    session = HarnessSession(
        project_id=project_id,
        session_factory=session_factory,
        env={"OPENTHEORY_ACTOR_JWT": token},
    )
    hold = await session.authorize()
    assert hold is not None

    revoked = await client.post(
        f"/api/v1/projects/{project_id}/agents/{agent_id}/tokens/{jti}/revoke",
        headers=_headers(owner_id),
    )
    assert revoked.status_code == 204, revoked.text

    spent = await session.record_spend(
        tokens_used=12,
        model="test-model",
        hold=hold,
    )
    assert spent is True
    debits = await _debit_rows(session_factory, project_id)
    assert len(debits) == 1
    assert str(debits[0].actor_id) == agent_id
    assert debits[0].tokens_used == 12

    later = HarnessSession(
        project_id=project_id,
        session_factory=session_factory,
        env={"OPENTHEORY_ACTOR_JWT": token},
    )
    try:
        await later.authorize()
        raise AssertionError("revoked token must refuse the next authorize")
    except TurnRefused as refused:
        assert refused.reason == REASON_ACTOR


async def test_authorize_refuses_when_session_and_mcp_credentials_differ(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    internal_funder,
    agent_secret,
) -> None:
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await create_owned_project(client, owner_id, "spend-diverge")
    agent_id = await _roster_crew(session_factory, project_id)
    minted = await _mint(client, project_id, agent_id, owner_id)

    session = HarnessSession(
        project_id=project_id,
        session_factory=session_factory,
        env={"OPENTHEORY_ACTOR_JWT": minted["token"]},
        actor_env={"OPENTHEORY_DEV_ACTOR_ID": owner_id},
    )
    try:
        await session.authorize()
        raise AssertionError("diverged session and MCP credentials must refuse")
    except TurnRefused as refused:
        assert refused.reason == REASON_CREDENTIAL_DIVERGENCE
    assert await _adjustments(session_factory, project_id) == []
    assert await _debit_rows(session_factory, project_id) == []


async def test_session_bind_still_stamps_when_mcp_side_has_no_credential(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    internal_funder,
    agent_secret,
) -> None:
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await create_owned_project(client, owner_id, "spend-bind")
    agent_id = await _roster_crew(session_factory, project_id)
    minted = await _mint(client, project_id, agent_id, owner_id)

    session = HarnessSession(
        project_id=project_id,
        session_factory=session_factory,
        env={"OPENTHEORY_ACTOR_JWT": minted["token"]},
        actor_env={"OPENTHEORY_GATEWAY_TOKEN": "not-an-actor"},
    )
    hold = await session.authorize()
    assert hold is not None
    spent = await session.record_spend(tokens_used=8, model="test-model", hold=hold)
    assert spent is True
    debits = await _debit_rows(session_factory, project_id)
    assert len(debits) == 1
    assert str(debits[0].actor_id) == agent_id
    assert str(debits[0].actor_id) != owner_id


async def test_zero_tokens_skips_spend_but_hold_release_keeps_actor(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    internal_funder,
    agent_secret,
) -> None:
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await create_owned_project(client, owner_id, "spend-zero")
    agent_id = await _roster_crew(session_factory, project_id)
    minted = await _mint(client, project_id, agent_id, owner_id)
    session = HarnessSession(
        project_id=project_id,
        session_factory=session_factory,
        env={"OPENTHEORY_ACTOR_JWT": minted["token"]},
    )
    hold = await session.authorize()
    assert hold is not None
    spent = await session.record_spend(tokens_used=0, model="test-model", hold=hold)
    assert spent is False
    assert await _debit_rows(session_factory, project_id) == []
    rows = await _adjustments(session_factory, project_id)
    assert len(rows) == 2
    assert all(row.amount == 0 for row in rows)
    assert all(str(row.actor_id) == agent_id for row in rows)
    assert all(SESSION_NOTES in (row.notes or "") for row in rows)


def _stub_planner(plan_result: PlanResult):
    calls = {"n": 0}

    async def _planner(
        thread, open_claims, catalog, model, *, llm, max_runs, grounding=None,
        observations=None, signals=None,
    ):
        calls["n"] += 1
        if calls["n"] == 1:
            return plan_result
        return PlanResult(runnable=[], proposed_count=0, tokens_used=0)

    return _planner


async def test_built_in_pass_debit_stamps_agent_actor(
    client: AsyncClient, session_factory: async_sessionmaker, internal_funder
) -> None:
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await create_owned_project(client, owner_id, "spend-pass")
    thread = await client.post(
        f"/api/v1/projects/{project_id}/threads",
        json={"title": "T", "question": "q?"},
        headers=_headers(owner_id),
    )
    assert thread.status_code == 201, thread.text
    note = await client.post(
        f"/api/v1/projects/{project_id}/checkpoints",
        json={"summary": "fork", "thread_id": thread.json()["id"]},
        headers=_headers(owner_id),
    )
    assert note.status_code == 201, note.text
    async with session_factory() as session:
        project = await session.get(Project, UUID(project_id))
        assert project is not None
        project.agent_models = {"researcher": "anthropic/claude-sonnet-4"}
        session.add(project)
        session.add(
            FundingAllocation(
                project_id=UUID(project_id),
                amount=Decimal("10.00"),
                currency="USD",
                kind=FundingKind.TOP_UP,
                source=FundingSource.NATIVE,
                status=FundingStatus.SETTLED,
            )
        )
        agent_run = AgentRun(
            project_id=UUID(project_id),
            thread_id=UUID(thread.json()["id"]),
            triggered_by_actor_id=UUID(owner_id),
            role="researcher",
            status=AgentRunStatus.RUNNING,
        )
        session.add(agent_run)
        await session.commit()
        run_id = agent_run.id

    async with session_factory() as session:
        result = await run_agent_pass(
            session,
            run_id,
            planner=_stub_planner(
                PlanResult(
                    runnable=[
                        PlannedRun(
                            instrument="calc.eval", inputs={"expression": "1 == 1"}
                        )
                    ],
                    proposed_count=1,
                    tokens_used=21,
                )
            ),
        )
        assert result.status is AgentRunStatus.COMPLETED, result.error
        assert result.agent_actor_id is not None
        debit = (
            await session.execute(
                select(ComputeDebit).where(ComputeDebit.agent_run_id == run_id)
            )
        ).scalar_one()
        assert debit.actor_id == result.agent_actor_id
        stamped = await session.get(Actor, debit.actor_id)
        assert stamped is not None
        assert stamped.type is ActorType.AGENT
