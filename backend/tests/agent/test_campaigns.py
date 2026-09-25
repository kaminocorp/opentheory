"""The continuous research campaign (0.25.0) — DB-backed.

Drives ``run_campaign`` with a **stub planner** so each cycle still goes through
the real 0.22.0 orchestrator and ``run_agent_pass`` chokepoint. Covers the
release's acceptance matrix: continues across cycles, stops on budget, stops on
no-work, honours cancel, and a failed cycle does not write Validation / funding.
"""

from decimal import Decimal
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agent.planner import PlanResult
from app.core.config import settings
from app.models.agent_run import AgentRun
from app.models.enums import ResearchCampaignStatus
from app.models.funding import FundingAllocation
from app.models.project import Project
from app.models.validation import Validation
from app.services.campaigns import (
    STOP_BUDGET_EXHAUSTED,
    STOP_CANCELLED,
    STOP_ERROR_BUDGET,
    STOP_MAX_CYCLES,
    STOP_NO_OPEN_WORK,
    request_cancel,
    run_campaign,
    start_campaign,
)
from app.services.compute import tokens_to_cost
from app.services.orchestration import STOP_MAX_PASSES
from tests.agent.test_orchestration import _one_calc, _start
from tests.agent.test_orchestrator import (
    _actor,
    _assign_model,
    _claim,
    _grant_budget,
    _project,
    _stub_planner,
    _thread,
    _thread_checkpoint,
)


async def _per_pass_calc(
    thread, open_claims, catalog, model, *, llm, max_runs, grounding=None, observations=None
):
    """One calc per pass (initial plan), empty on replan — safe across campaign cycles."""
    if observations is None:
        return _one_calc()
    return PlanResult(runnable=[], proposed_count=0, tokens_used=0)


async def _start_campaign(
    session_factory: async_sessionmaker,
    project_id: str,
    actor_id: str,
    role: str = "researcher",
    max_cycles: int | None = None,
) -> UUID:
    async with session_factory() as session:
        from app.models.actor import Actor

        actor = await session.get(Actor, UUID(actor_id))
        campaign = await start_campaign(
            session,
            UUID(project_id),
            triggered_by=actor,
            role=role,
            max_cycles=max_cycles,
        )
        return campaign.id


async def test_empty_project_stops_on_no_open_work(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client, "camp-empty")
    await _assign_model(session_factory, project_id)
    campaign_id = await _start_campaign(session_factory, project_id, actor_id)

    called = {"n": 0}

    async def _boom(
        thread, open_claims, catalog, model, *, llm, max_runs, grounding=None, observations=None
    ):
        called["n"] += 1
        raise AssertionError("planner must not run when there is no open work")

    async with session_factory() as session:
        result = await run_campaign(session, campaign_id, planner=_boom)

    assert result.status is ResearchCampaignStatus.COMPLETED
    assert result.stop_reason == STOP_NO_OPEN_WORK
    assert result.current_cycle == 0
    assert result.cycles_completed == 0
    assert result.cycles == []
    assert called["n"] == 0
    async with session_factory() as session:
        assert (await session.execute(select(func.count()).select_from(AgentRun))).scalar() == 0
        assert (await session.execute(select(func.count()).select_from(Validation))).scalar() == 0


async def test_unfunded_project_with_work_stops_on_budget(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client, "camp-broke")
    thread_id = await _thread(client, project_id, actor_id)
    await _claim(client, thread_id, actor_id, "Would raise.")
    async with session_factory() as session:
        project = await session.get(Project, UUID(project_id))
        project.agent_models = {"researcher": "anthropic/claude-sonnet-4"}
        await session.commit()
    campaign_id = await _start_campaign(session_factory, project_id, actor_id)

    called = {"n": 0}

    async def _boom(
        thread, open_claims, catalog, model, *, llm, max_runs, grounding=None, observations=None
    ):
        called["n"] += 1
        raise AssertionError("planner must not run when the project pot is empty")

    async with session_factory() as session:
        result = await run_campaign(session, campaign_id, planner=_boom)

    assert result.status is ResearchCampaignStatus.COMPLETED
    assert result.stop_reason == STOP_BUDGET_EXHAUSTED
    assert result.current_cycle == 0
    assert result.cycles_completed == 0
    assert called["n"] == 0


async def test_continues_across_cycles_when_pass_cap_leaves_work(
    client: AsyncClient, session_factory: async_sessionmaker, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One orchestration's max_passes is not the campaign stop — the next cycle continues."""
    monkeypatch.setattr(settings, "orchestration_max_passes", 1)
    monkeypatch.setattr(settings, "campaign_max_cycles", 2)
    actor_id = await _actor(client)
    project_id = await _project(client, "camp-cycles")
    t1 = await _thread(client, project_id, actor_id)
    t2 = await _thread(client, project_id, actor_id)
    await _claim(client, t1, actor_id, "First.")
    await _claim(client, t2, actor_id, "Second.")
    await _thread_checkpoint(client, project_id, t1, actor_id)
    await _thread_checkpoint(client, project_id, t2, actor_id)
    await _assign_model(session_factory, project_id)
    campaign_id = await _start_campaign(session_factory, project_id, actor_id, max_cycles=2)

    async with session_factory() as session:
        result = await run_campaign(session, campaign_id, planner=_per_pass_calc)

    assert result.status is ResearchCampaignStatus.COMPLETED
    assert result.stop_reason == STOP_MAX_CYCLES
    assert result.current_cycle == 2
    assert result.cycles_completed == 2
    assert len(result.cycles) == 2
    assert result.cycles[0]["cycle"] == 1
    assert result.cycles[1]["cycle"] == 2
    assert result.cycles[0]["orchestration_id"] != result.cycles[1]["orchestration_id"]
    assert result.cycles[0]["stop_reason"] == STOP_MAX_PASSES
    assert result.cycles[0]["passes_commissioned"] == 1
    assert result.cycles[1]["passes_commissioned"] == 1
    assert all(row["orchestration_status"] == "completed" for row in result.cycles)


async def test_budget_stops_campaign_after_a_spent_cycle(
    client: AsyncClient, session_factory: async_sessionmaker, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "agent_token_rate_usd_per_1k", Decimal("1.00"))
    monkeypatch.setattr(settings, "orchestration_max_passes", 1)
    monkeypatch.setattr(settings, "campaign_max_cycles", 8)
    actor_id = await _actor(client)
    project_id = await _project(client, "camp-budget")
    t1 = await _thread(client, project_id, actor_id)
    t2 = await _thread(client, project_id, actor_id)
    await _claim(client, t1, actor_id, "Spender.")
    await _claim(client, t2, actor_id, "Left for later.")
    await _thread_checkpoint(client, project_id, t1, actor_id)
    await _thread_checkpoint(client, project_id, t2, actor_id)
    await _assign_model(session_factory, project_id, budget=None)
    await _grant_budget(session_factory, project_id, amount="1.00")
    campaign_id = await _start_campaign(session_factory, project_id, actor_id)

    plan = _one_calc(tokens_used=1000)
    assert tokens_to_cost(1000, Decimal("1.00")) == Decimal("1.000000")

    async with session_factory() as session:
        result = await run_campaign(session, campaign_id, planner=_stub_planner(plan))

    assert result.status is ResearchCampaignStatus.COMPLETED
    assert result.stop_reason == STOP_BUDGET_EXHAUSTED
    assert result.cycles_completed == 1
    assert result.cycles[0]["stop_reason"] == STOP_BUDGET_EXHAUSTED
    assert Decimal(str(result.budget_available_end)) <= 0


async def test_cancel_before_first_cycle_stops_without_commissioning(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client, "camp-cancel")
    t1 = await _thread(client, project_id, actor_id)
    await _claim(client, t1, actor_id, "Would raise.")
    await _thread_checkpoint(client, project_id, t1, actor_id)
    await _assign_model(session_factory, project_id)
    campaign_id = await _start_campaign(session_factory, project_id, actor_id)

    async with session_factory() as session:
        cancelled = await request_cancel(session, campaign_id)
        assert cancelled.cancel_requested is True
        result = await run_campaign(session, campaign_id, planner=_stub_planner(_one_calc()))

    assert result.status is ResearchCampaignStatus.COMPLETED
    assert result.stop_reason == STOP_CANCELLED
    assert result.current_cycle == 0
    assert result.cycles_completed == 0
    async with session_factory() as session:
        assert (await session.execute(select(func.count()).select_from(AgentRun))).scalar() == 0


async def test_cancel_after_first_cycle_stops_before_the_next(
    client: AsyncClient, session_factory: async_sessionmaker, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "orchestration_max_passes", 1)
    monkeypatch.setattr(settings, "campaign_max_cycles", 8)
    actor_id = await _actor(client)
    project_id = await _project(client, "camp-cancel-mid")
    t1 = await _thread(client, project_id, actor_id)
    t2 = await _thread(client, project_id, actor_id)
    await _claim(client, t1, actor_id, "First.")
    await _claim(client, t2, actor_id, "Second.")
    await _thread_checkpoint(client, project_id, t1, actor_id)
    await _thread_checkpoint(client, project_id, t2, actor_id)
    await _assign_model(session_factory, project_id)
    campaign_id = await _start_campaign(session_factory, project_id, actor_id)
    ok_stub = _stub_planner(_one_calc())

    async def _planner(
        thread, open_claims, catalog, model, *, llm, max_runs, grounding=None, observations=None
    ):
        async with session_factory() as inner:
            await request_cancel(inner, campaign_id)
        return await ok_stub(
            thread,
            open_claims,
            catalog,
            model,
            llm=llm,
            max_runs=max_runs,
            grounding=grounding,
            observations=observations,
        )

    async with session_factory() as session:
        result = await run_campaign(session, campaign_id, planner=_planner)

    assert result.status is ResearchCampaignStatus.COMPLETED
    assert result.stop_reason == STOP_CANCELLED
    assert result.cycles_completed == 1
    assert result.current_cycle == 1


async def test_error_budget_stops_after_consecutive_failed_cycles(
    client: AsyncClient, session_factory: async_sessionmaker, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "campaign_error_budget", 2)
    monkeypatch.setattr(settings, "campaign_max_cycles", 8)
    actor_id = await _actor(client)
    project_id = await _project(client, "camp-errors")
    t1 = await _thread(client, project_id, actor_id)
    await _claim(client, t1, actor_id, "Would raise.")
    await _thread_checkpoint(client, project_id, t1, actor_id)
    await _assign_model(session_factory, project_id)
    campaign_id = await _start_campaign(session_factory, project_id, actor_id)

    async def _explode(db, orchestration_id, **kwargs):
        raise RuntimeError("cycle exploded")

    monkeypatch.setattr("app.services.orchestration.run_orchestration", _explode)

    async with session_factory() as session:
        result = await run_campaign(session, campaign_id, planner=_stub_planner(_one_calc()))

    assert result.status is ResearchCampaignStatus.COMPLETED
    assert result.stop_reason == STOP_ERROR_BUDGET
    assert result.consecutive_errors == 2
    assert result.current_cycle == 2
    assert len(result.cycles) == 2
    assert all(row["error"] for row in result.cycles)


async def test_campaign_does_not_write_validation_or_funding(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client, "camp-ledger")
    t1 = await _thread(client, project_id, actor_id)
    await _claim(client, t1, actor_id, "A raisable claim.")
    await _thread_checkpoint(client, project_id, t1, actor_id)
    await _assign_model(session_factory, project_id)

    async with session_factory() as session:
        before_validations = (
            await session.execute(select(func.count()).select_from(Validation))
        ).scalar()
        before_funds = (
            await session.execute(select(func.count()).select_from(FundingAllocation))
        ).scalar()

    campaign_id = await _start_campaign(session_factory, project_id, actor_id)
    async with session_factory() as session:
        result = await run_campaign(session, campaign_id, planner=_stub_planner(_one_calc()))

    assert result.status is ResearchCampaignStatus.COMPLETED
    assert result.cycles_completed == 1
    async with session_factory() as session:
        after_validations = (
            await session.execute(select(func.count()).select_from(Validation))
        ).scalar()
        after_funds = (
            await session.execute(select(func.count()).select_from(FundingAllocation))
        ).scalar()
        assert after_validations == before_validations == 0
        assert after_funds == before_funds


async def test_running_campaign_blocks_a_standalone_orchestration(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client, "camp-blocks-orch")
    await _assign_model(session_factory, project_id)
    await _start_campaign(session_factory, project_id, actor_id)

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await _start(session_factory, project_id, actor_id)
    assert exc.value.status_code == 409
