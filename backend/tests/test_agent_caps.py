"""0.58.0 — lifetime per-seat agent caps on authorize and the built-in pass.

DB-gated. The shared project daily cap stays; this is not a split.
Definition catalog (slice G) stays out.
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
    REASON_AGENT_TOKEN_CAP,
    REASON_AGENT_USD_CAP,
    REASON_DAILY_CAP,
    SESSION_NOTES,
    HarnessSession,
    TurnRefused,
    is_daily_cap_adjustment,
    load_today_adjustments,
)
from app.models.agent_run import AgentRun
from app.models.compute_debit import ComputeDebit
from app.models.enums import (
    AgentRunStatus,
    ComputeDebitKind,
    ComputeDebitRateSource,
    FundingKind,
    FundingSource,
    FundingStatus,
)
from app.models.funding import FundingAllocation
from app.models.project import Project
from app.services.agent_actors import get_or_create_project_agent_actor
from app.services.agent_caps import (
    AgentCapRoom,
    agent_token_room_for_clamp,
    refuse_reason,
)
from app.services.agent_runs import AGENT_CAP_EXHAUSTED_REASON, run_agent_pass
from app.services.harness_meter import turn_clamp
from tests.principals import create_owned_project

TEST_SECRET = "test-agent-session-secret-0.58.0-32b!!"


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


async def _set_caps(
    client: AsyncClient,
    project_id: str,
    actor_id: str,
    owner_id: str,
    *,
    token_budget_cap: int | None = None,
    usd_budget_cap: str | None = None,
    fields: set[str] | None = None,
) -> None:
    body: dict = {}
    chosen = fields if fields is not None else {
        name
        for name, value in (
            ("token_budget_cap", token_budget_cap),
            ("usd_budget_cap", usd_budget_cap),
        )
        if value is not None
    }
    if "token_budget_cap" in chosen:
        body["token_budget_cap"] = token_budget_cap
    if "usd_budget_cap" in chosen:
        body["usd_budget_cap"] = usd_budget_cap
    resp = await client.patch(
        f"/api/v1/projects/{project_id}/agents/{actor_id}",
        json=body,
        headers=_headers(owner_id),
    )
    assert resp.status_code == 200, resp.text


async def _bill(
    session_factory: async_sessionmaker,
    project_id: str,
    actor_id: str,
    *,
    tokens_used: int,
    amount: Decimal,
) -> None:
    async with session_factory() as session:
        session.add(
            ComputeDebit(
                project_id=UUID(project_id),
                actor_id=UUID(actor_id),
                tokens_used=tokens_used,
                amount=amount,
                currency="USD",
                rate_per_1k=Decimal("5"),
                rate_source=ComputeDebitRateSource.BLENDED_FALLBACK,
                kind=ComputeDebitKind.PLANNING,
                notes=f"{SESSION_NOTES}; billed",
            )
        )
        await session.commit()


async def _adjustments(session_factory: async_sessionmaker, project_id: str):
    async with session_factory() as session:
        return await load_today_adjustments(session, UUID(project_id))


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


def _stub_planner(plan_result: PlanResult):
    calls = {"n": 0}

    async def _planner(
        *args,
        observations=None,
        signals=None,
        **kwargs,
    ):
        calls["n"] += 1
        if calls["n"] == 1:
            return plan_result
        return PlanResult(runnable=[], proposed_count=0, tokens_used=0)

    _planner.calls = calls  # type: ignore[attr-defined]
    return _planner


def test_refuse_reason_and_clamp_room_are_lifetime_math() -> None:
    unlimited = AgentCapRoom(
        token_cap=None,
        usd_cap=None,
        tokens_billed=0,
        amount_billed=Decimal("0"),
        tokens_held=0,
        token_remaining=None,
        usd_remaining=None,
    )
    assert refuse_reason(unlimited) is None
    assert agent_token_room_for_clamp(unlimited, rate_per_1k=Decimal("1.00")) is None

    token_done = AgentCapRoom(
        token_cap=50,
        usd_cap=None,
        tokens_billed=50,
        amount_billed=Decimal("0"),
        tokens_held=0,
        token_remaining=0,
        usd_remaining=None,
    )
    assert refuse_reason(token_done) == REASON_AGENT_TOKEN_CAP

    usd_done = AgentCapRoom(
        token_cap=1_000,
        usd_cap=Decimal("0.20"),
        tokens_billed=10,
        amount_billed=Decimal("0.20"),
        tokens_held=0,
        token_remaining=990,
        usd_remaining=Decimal("0"),
    )
    assert refuse_reason(usd_done) == REASON_AGENT_USD_CAP

    leftover = AgentCapRoom(
        token_cap=1_000,
        usd_cap=Decimal("0.05"),
        tokens_billed=10,
        amount_billed=Decimal("0"),
        tokens_held=0,
        token_remaining=990,
        usd_remaining=Decimal("0.05"),
    )
    assert agent_token_room_for_clamp(leftover, rate_per_1k=Decimal("1.00")) == 50
    assert agent_token_room_for_clamp(leftover, rate_per_1k=None) == 990
    assert turn_clamp(daily_room=20_000, pot_room=80, agent_room=50) == 50


async def test_null_caps_still_authorize(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    internal_funder,
    agent_secret,
) -> None:
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await create_owned_project(client, owner_id, "caps-null")
    agent_id = await _roster_crew(session_factory, project_id)
    minted = await _mint(client, project_id, agent_id, owner_id)
    session = HarnessSession(
        project_id=project_id,
        session_factory=session_factory,
        env={"OPENTHEORY_ACTOR_JWT": minted["token"]},
    )
    hold = await session.authorize()
    assert hold is not None
    assert hold.tokens > 0
    rows = await _adjustments(session_factory, project_id)
    assert len([row for row in rows if "daily_cap_hold" in (row.notes or "")]) == 1


async def test_human_authorize_has_no_per_agent_cap(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    internal_funder,
) -> None:
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await create_owned_project(client, owner_id, "caps-human")
    session = HarnessSession(
        project_id=project_id,
        session_factory=session_factory,
        env={"OPENTHEORY_DEV_ACTOR_ID": owner_id},
    )
    hold = await session.authorize()
    assert hold is not None


async def test_token_cap_reached_refuses_without_hold(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    internal_funder,
    agent_secret,
) -> None:
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await create_owned_project(client, owner_id, "caps-token")
    agent_id = await _roster_crew(session_factory, project_id)
    await _set_caps(client, project_id, agent_id, owner_id, token_budget_cap=40)
    await _bill(session_factory, project_id, agent_id, tokens_used=40, amount=Decimal("0.10"))
    minted = await _mint(client, project_id, agent_id, owner_id)
    session = HarnessSession(
        project_id=project_id,
        session_factory=session_factory,
        env={"OPENTHEORY_ACTOR_JWT": minted["token"]},
    )
    try:
        await session.authorize()
        raise AssertionError("reached token cap must refuse")
    except TurnRefused as refused:
        assert refused.reason == REASON_AGENT_TOKEN_CAP
    holds = [
        row
        for row in await _adjustments(session_factory, project_id)
        if "daily_cap_hold" in (row.notes or "")
    ]
    assert holds == []


async def test_usd_cap_reached_refuses_without_hold(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    internal_funder,
    agent_secret,
) -> None:
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await create_owned_project(client, owner_id, "caps-usd")
    agent_id = await _roster_crew(session_factory, project_id)
    await _set_caps(client, project_id, agent_id, owner_id, usd_budget_cap="0.20")
    await _bill(session_factory, project_id, agent_id, tokens_used=10, amount=Decimal("0.20"))
    minted = await _mint(client, project_id, agent_id, owner_id)
    session = HarnessSession(
        project_id=project_id,
        session_factory=session_factory,
        env={"OPENTHEORY_ACTOR_JWT": minted["token"]},
    )
    try:
        await session.authorize()
        raise AssertionError("reached usd cap must refuse")
    except TurnRefused as refused:
        assert refused.reason == REASON_AGENT_USD_CAP
    holds = [
        row
        for row in await _adjustments(session_factory, project_id)
        if "daily_cap_hold" in (row.notes or "")
    ]
    assert holds == []


async def test_remaining_token_cap_clamps_max_tokens_not_hold_occupancy(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    internal_funder,
    agent_secret,
) -> None:
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await create_owned_project(client, owner_id, "caps-clamp")
    agent_id = await _roster_crew(session_factory, project_id)
    await _set_caps(client, project_id, agent_id, owner_id, token_budget_cap=50)
    minted = await _mint(client, project_id, agent_id, owner_id)
    session = HarnessSession(
        project_id=project_id,
        session_factory=session_factory,
        env={"OPENTHEORY_ACTOR_JWT": minted["token"]},
    )
    hold = await session.authorize()
    assert hold is not None
    assert hold.clamp == 50
    assert hold.tokens == hold.daily_room
    assert hold.tokens > 50


async def test_unfunded_with_a_cap_is_not_exhausted(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    internal_funder,
    agent_secret,
) -> None:
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await create_owned_project(client, owner_id, "caps-unfunded")
    agent_id = await _roster_crew(session_factory, project_id)
    await _set_caps(client, project_id, agent_id, owner_id, token_budget_cap=80)
    minted = await _mint(client, project_id, agent_id, owner_id)
    session = HarnessSession(
        project_id=project_id,
        session_factory=session_factory,
        env={"OPENTHEORY_ACTOR_JWT": minted["token"]},
    )
    hold = await session.authorize()
    assert hold is not None
    assert hold.clamp == 80


async def test_overlapping_authorize_second_refuses_no_second_hold(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    internal_funder,
    agent_secret,
) -> None:
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await create_owned_project(client, owner_id, "caps-race")
    agent_id = await _roster_crew(session_factory, project_id)
    await _set_caps(client, project_id, agent_id, owner_id, token_budget_cap=80)
    minted = await _mint(client, project_id, agent_id, owner_id)
    first = HarnessSession(
        project_id=project_id,
        session_factory=session_factory,
        env={"OPENTHEORY_ACTOR_JWT": minted["token"]},
    )
    hold = await first.authorize()
    assert hold is not None
    second = HarnessSession(
        project_id=project_id,
        session_factory=session_factory,
        env={"OPENTHEORY_ACTOR_JWT": minted["token"]},
    )
    try:
        await second.authorize()
        raise AssertionError("overlapping authorize must refuse")
    except TurnRefused as refused:
        assert refused.reason in {REASON_DAILY_CAP, REASON_AGENT_TOKEN_CAP}
    holds = [
        row
        for row in await _adjustments(session_factory, project_id)
        if "daily_cap_hold" in (row.notes or "")
    ]
    assert len(holds) == 1


async def test_mid_turn_spend_over_cap_still_writes(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    internal_funder,
    agent_secret,
) -> None:
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await create_owned_project(client, owner_id, "caps-mid")
    agent_id = await _roster_crew(session_factory, project_id)
    await _set_caps(client, project_id, agent_id, owner_id, token_budget_cap=40)
    minted = await _mint(client, project_id, agent_id, owner_id)
    session = HarnessSession(
        project_id=project_id,
        session_factory=session_factory,
        env={"OPENTHEORY_ACTOR_JWT": minted["token"]},
    )
    hold = await session.authorize()
    assert hold is not None
    spent = await session.record_spend(
        tokens_used=80,
        model="test-model",
        hold=hold,
    )
    assert spent is True
    debits = await _debit_rows(session_factory, project_id)
    assert len(debits) == 1
    assert debits[0].tokens_used == 80
    assert str(debits[0].actor_id) == agent_id

    later = HarnessSession(
        project_id=project_id,
        session_factory=session_factory,
        env={"OPENTHEORY_ACTOR_JWT": minted["token"]},
    )
    try:
        await later.authorize()
        raise AssertionError("next authorize after over-cap spend must refuse")
    except TurnRefused as refused:
        assert refused.reason == REASON_AGENT_TOKEN_CAP


async def test_clearing_a_reached_cap_authorizes_again(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    internal_funder,
    agent_secret,
) -> None:
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await create_owned_project(client, owner_id, "caps-clear")
    agent_id = await _roster_crew(session_factory, project_id)
    await _set_caps(client, project_id, agent_id, owner_id, token_budget_cap=20)
    await _bill(session_factory, project_id, agent_id, tokens_used=20, amount=Decimal("0.05"))
    minted = await _mint(client, project_id, agent_id, owner_id)
    blocked = HarnessSession(
        project_id=project_id,
        session_factory=session_factory,
        env={"OPENTHEORY_ACTOR_JWT": minted["token"]},
    )
    try:
        await blocked.authorize()
        raise AssertionError("reached cap must refuse before clear")
    except TurnRefused as refused:
        assert refused.reason == REASON_AGENT_TOKEN_CAP

    await _set_caps(
        client,
        project_id,
        agent_id,
        owner_id,
        token_budget_cap=None,
        fields={"token_budget_cap"},
    )
    later = HarnessSession(
        project_id=project_id,
        session_factory=session_factory,
        env={"OPENTHEORY_ACTOR_JWT": minted["token"]},
    )
    hold = await later.authorize()
    assert hold is not None


async def test_built_in_pass_refuses_before_planner_when_cap_reached(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    internal_funder,
) -> None:
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await create_owned_project(client, owner_id, "caps-pass-start")
    agent_id = await _roster_crew(session_factory, project_id)
    await _set_caps(client, project_id, agent_id, owner_id, token_budget_cap=10)
    await _bill(session_factory, project_id, agent_id, tokens_used=10, amount=Decimal("0.02"))
    thread = await client.post(
        f"/api/v1/projects/{project_id}/threads",
        json={"title": "T", "question": "q?"},
        headers=_headers(owner_id),
    )
    assert thread.status_code == 201, thread.text
    async with session_factory() as session:
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

    async def boom(*args, **kwargs):
        raise AssertionError("planner must not run when the agent cap is already reached")

    async with session_factory() as session:
        result = await run_agent_pass(session, run_id, planner=boom)
        assert result.status is AgentRunStatus.FAILED
        assert result.error == REASON_AGENT_TOKEN_CAP


async def test_built_in_pass_skips_remaining_after_planning_hits_cap(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    internal_funder,
) -> None:
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await create_owned_project(client, owner_id, "caps-pass-mid")
    agent_id = await _roster_crew(session_factory, project_id)
    await _set_caps(client, project_id, agent_id, owner_id, token_budget_cap=21)
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

    planner = _stub_planner(
        PlanResult(
            runnable=[
                PlannedRun(instrument="calc.eval", inputs={"expression": "1 == 1"})
            ],
            proposed_count=1,
            tokens_used=21,
        )
    )
    async with session_factory() as session:
        result = await run_agent_pass(session, run_id, planner=planner)
        assert result.status is AgentRunStatus.COMPLETED, result.error
        skipped = [step for step in (result.steps or []) if step.get("status") == "skipped"]
        assert skipped
        assert skipped[0].get("reason") == AGENT_CAP_EXHAUSTED_REASON
        debit = (
            await session.execute(select(ComputeDebit).where(ComputeDebit.agent_run_id == run_id))
        ).scalar_one()
        assert debit.tokens_used == 21
        assert str(debit.actor_id) == agent_id
