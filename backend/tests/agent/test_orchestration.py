"""The project-level multi-thread orchestrator (0.22.0) — DB-backed.

Drives ``run_orchestration`` with a **stub planner** so the loop is deterministic while
each commissioned ``run_agent_pass`` still goes through the real chokepoint. Covers
the release's acceptance matrix: budget stops the loop, multiple threads get passes,
empty/no-work exits cleanly, and a failed sub-pass does not corrupt the ledger
(no validation, no funding write, earlier checkpoints stand).
"""

from decimal import Decimal
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agent.llm import AgentLlmError
from app.agent.planner import PlannedRun, PlanResult
from app.core.config import settings
from app.models.agent_run import AgentRun
from app.models.checkpoint import Checkpoint
from app.models.enums import AgentRunStatus, OrchestrationRunStatus, ThreadStatus
from app.models.funding import FundingAllocation
from app.models.project import Project
from app.models.thread import Thread
from app.models.validation import Validation
from app.services.compute import tokens_to_cost
from app.services.orchestration import (
    STOP_BUDGET_EXHAUSTED,
    STOP_MAX_PASSES,
    STOP_NO_OPEN_WORK,
    run_orchestration,
    start_orchestration,
)
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


def _one_calc(*, tokens_used: int = 10) -> PlanResult:
    return PlanResult(
        runnable=[
            PlannedRun(
                instrument="calc.eval",
                inputs={"expression": "1 + 1"},
                rationale="smoke",
            )
        ],
        dropped=[],
        tokens_used=tokens_used,
        proposed_count=1,
    )


async def _start(
    session_factory: async_sessionmaker,
    project_id: str,
    actor_id: str,
    role: str = "researcher",
) -> UUID:
    async with session_factory() as session:
        from app.models.actor import Actor

        actor = await session.get(Actor, UUID(actor_id))
        run = await start_orchestration(
            session, UUID(project_id), triggered_by=actor, role=role
        )
        return run.id


async def test_empty_project_exits_cleanly_with_no_open_work(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client, "orch-empty")
    await _assign_model(session_factory, project_id)
    orch_id = await _start(session_factory, project_id, actor_id)

    called = {"n": 0}

    async def _boom(
        thread, open_claims, catalog, model, *, llm, max_runs, grounding=None, observations=None
    ):
        called["n"] += 1
        raise AssertionError("planner must not run when there is no open work")

    async with session_factory() as session:
        result = await run_orchestration(session, orch_id, planner=_boom)

    assert result.status is OrchestrationRunStatus.COMPLETED
    assert result.stop_reason == STOP_NO_OPEN_WORK
    assert result.passes_commissioned == 0
    assert result.passes_completed == 0
    assert result.passes_failed == 0
    assert called["n"] == 0
    async with session_factory() as session:
        assert (await session.execute(select(func.count()).select_from(AgentRun))).scalar() == 0
        assert (await session.execute(select(func.count()).select_from(Validation))).scalar() == 0


async def test_thread_without_claims_is_skipped(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client, "orch-noclaim")
    await _thread(client, project_id, actor_id)
    await _assign_model(session_factory, project_id)
    orch_id = await _start(session_factory, project_id, actor_id)

    async with session_factory() as session:
        result = await run_orchestration(session, orch_id, planner=_stub_planner(_one_calc()))

    assert result.status is OrchestrationRunStatus.COMPLETED
    assert result.stop_reason == STOP_NO_OPEN_WORK
    assert result.passes_commissioned == 0
    assert result.passes_skipped == 1
    assert result.decisions[0]["action"] == "skipped"
    assert result.decisions[0]["reason"] == "no_open_claims"


async def test_closed_thread_is_skipped(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client, "orch-closed")
    thread_id = await _thread(client, project_id, actor_id)
    await _claim(client, thread_id, actor_id, "A closed line.")
    await _assign_model(session_factory, project_id)
    async with session_factory() as session:
        thread = await session.get(Thread, UUID(thread_id))
        thread.status = ThreadStatus.CLOSED
        await session.commit()
    orch_id = await _start(session_factory, project_id, actor_id)

    async with session_factory() as session:
        result = await run_orchestration(session, orch_id, planner=_stub_planner(_one_calc()))

    assert result.passes_commissioned == 0
    assert result.decisions[0]["reason"] == "thread_not_open"
    assert result.stop_reason == STOP_NO_OPEN_WORK


async def test_multiple_threads_each_get_a_pass(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client, "orch-multi")
    t1 = await _thread(client, project_id, actor_id)
    t2 = await _thread(client, project_id, actor_id)
    await _claim(client, t1, actor_id, "First thread claim.")
    await _claim(client, t2, actor_id, "Second thread claim.")
    await _thread_checkpoint(client, project_id, t1, actor_id)
    await _thread_checkpoint(client, project_id, t2, actor_id)
    await _assign_model(session_factory, project_id)
    orch_id = await _start(session_factory, project_id, actor_id)

    async with session_factory() as session:
        result = await run_orchestration(session, orch_id, planner=_stub_planner(_one_calc()))

    assert result.status is OrchestrationRunStatus.COMPLETED
    assert result.stop_reason == STOP_NO_OPEN_WORK
    assert result.passes_commissioned == 2
    assert result.passes_completed == 2
    assert result.passes_failed == 0
    commissioned = [d for d in result.decisions if d["action"] == "commissioned"]
    assert {d["thread_id"] for d in commissioned} == {t1, t2}
    assert all(d["agent_run_id"] for d in commissioned)
    assert all(d["agent_run_status"] == "completed" for d in commissioned)
    assert result.budget_available_end is not None
    assert result.budget_available_start is not None
    assert result.budget_available_end < result.budget_available_start


async def test_budget_stops_orchestration_before_a_second_thread(
    client: AsyncClient, session_factory: async_sessionmaker, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pot that covers one planning debit commissions the first thread and skips the rest."""
    monkeypatch.setattr(settings, "agent_token_rate_usd_per_1k", Decimal("1.00"))
    actor_id = await _actor(client)
    project_id = await _project(client, "orch-budget")
    t1 = await _thread(client, project_id, actor_id)
    t2 = await _thread(client, project_id, actor_id)
    await _claim(client, t1, actor_id, "Spender.")
    await _claim(client, t2, actor_id, "Never reached.")
    await _thread_checkpoint(client, project_id, t1, actor_id)
    await _thread_checkpoint(client, project_id, t2, actor_id)
    # Default _assign_model grants $100; overwrite with a pot that one 1-token debit empties.
    await _assign_model(session_factory, project_id, budget=None)
    await _grant_budget(session_factory, project_id, amount="1.00")
    orch_id = await _start(session_factory, project_id, actor_id)

    # 1 token at $1/1k = $0.001; grant is $1.00 so that would NOT stop. Use enough tokens
    # to consume the whole pot: 1000 tokens × $1/1k = $1.00.
    plan = _one_calc(tokens_used=1000)
    expected = tokens_to_cost(1000, Decimal("1.00"))
    assert expected == Decimal("1.000000")

    async with session_factory() as session:
        result = await run_orchestration(session, orch_id, planner=_stub_planner(plan))

    assert result.status is OrchestrationRunStatus.COMPLETED
    assert result.stop_reason == STOP_BUDGET_EXHAUSTED
    assert result.passes_commissioned == 1
    assert result.passes_completed == 1
    assert result.passes_skipped == 1
    commissioned = [d for d in result.decisions if d["action"] == "commissioned"]
    skipped = [d for d in result.decisions if d["action"] == "skipped"]
    assert commissioned[0]["thread_id"] == t1
    assert skipped[0]["thread_id"] == t2
    assert skipped[0]["reason"] == "budget_exhausted"
    assert Decimal(str(result.budget_available_end)) <= 0


async def test_unfunded_project_with_work_stops_on_budget(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client, "orch-broke")
    thread_id = await _thread(client, project_id, actor_id)
    await _claim(client, thread_id, actor_id, "Would raise.")
    # Assign a model but grant no budget (available = 0).
    async with session_factory() as session:
        project = await session.get(Project, UUID(project_id))
        project.agent_models = {"researcher": "anthropic/claude-sonnet-4"}
        await session.commit()
    orch_id = await _start(session_factory, project_id, actor_id)

    called = {"n": 0}

    async def _boom(
        thread, open_claims, catalog, model, *, llm, max_runs, grounding=None, observations=None
    ):
        called["n"] += 1
        raise AssertionError("planner must not run when the project pot is empty")

    async with session_factory() as session:
        result = await run_orchestration(session, orch_id, planner=_boom)

    assert result.status is OrchestrationRunStatus.COMPLETED
    assert result.stop_reason == STOP_BUDGET_EXHAUSTED
    assert result.passes_commissioned == 0
    assert result.decisions[0]["reason"] == "budget_exhausted"
    assert called["n"] == 0
    async with session_factory() as session:
        assert (await session.execute(select(func.count()).select_from(AgentRun))).scalar() == 0


async def test_failed_subpass_does_not_corrupt_the_ledger(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    """A planner failure on thread 1 still lets thread 2 land; no Validation / fund write."""
    actor_id = await _actor(client)
    project_id = await _project(client, "orch-fail")
    fail_id = await _thread(client, project_id, actor_id)
    ok_id = await _thread(client, project_id, actor_id)
    await _claim(client, fail_id, actor_id, "This pass will fail.")
    await _claim(client, ok_id, actor_id, "This pass will land.")
    await _thread_checkpoint(client, project_id, fail_id, actor_id)
    await _thread_checkpoint(client, project_id, ok_id, actor_id)
    await _assign_model(session_factory, project_id)

    async with session_factory() as session:
        before_checkpoints = (
            await session.execute(select(func.count()).select_from(Checkpoint))
        ).scalar()
        before_validations = (
            await session.execute(select(func.count()).select_from(Validation))
        ).scalar()
        before_funds = (
            await session.execute(select(func.count()).select_from(FundingAllocation))
        ).scalar()

    async def _planner(
        thread, open_claims, catalog, model, *, llm, max_runs, grounding=None, observations=None
    ):
        if str(thread.id) == fail_id:
            raise AgentLlmError("planner failed on purpose")
        return _one_calc()

    orch_id = await _start(session_factory, project_id, actor_id)
    async with session_factory() as session:
        result = await run_orchestration(session, orch_id, planner=_planner)

    assert result.status is OrchestrationRunStatus.COMPLETED
    assert result.passes_commissioned == 2
    assert result.passes_failed == 1
    assert result.passes_completed == 1
    by_thread = {d["thread_id"]: d for d in result.decisions}
    assert by_thread[fail_id]["action"] == "commissioned"
    assert by_thread[fail_id]["agent_run_status"] == "failed"
    assert by_thread[ok_id]["agent_run_status"] == "completed"

    async with session_factory() as session:
        after_validations = (
            await session.execute(select(func.count()).select_from(Validation))
        ).scalar()
        after_funds = (
            await session.execute(select(func.count()).select_from(FundingAllocation))
        ).scalar()
        after_checkpoints = (
            await session.execute(select(func.count()).select_from(Checkpoint))
        ).scalar()
        # The orchestrator is contributor infrastructure: it never self-validates
        # and never writes a FundingAllocation (the seed grant is the only row).
        assert after_validations == before_validations == 0
        assert after_funds == before_funds
        # The failed pass minted nothing; the successful one may have forked + landed.
        assert after_checkpoints >= before_checkpoints
        failed_run = await session.get(AgentRun, UUID(by_thread[fail_id]["agent_run_id"]))
        assert failed_run.status is AgentRunStatus.FAILED
        assert failed_run.ran_count == 0
        ok_run = await session.get(AgentRun, UUID(by_thread[ok_id]["agent_run_id"]))
        assert ok_run.status is AgentRunStatus.COMPLETED
        assert ok_run.ran_count == 1


async def test_max_passes_cap_skips_remaining_threads(
    client: AsyncClient, session_factory: async_sessionmaker, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "orchestration_max_passes", 1)
    actor_id = await _actor(client)
    project_id = await _project(client, "orch-cap")
    t1 = await _thread(client, project_id, actor_id)
    t2 = await _thread(client, project_id, actor_id)
    await _claim(client, t1, actor_id, "First.")
    await _claim(client, t2, actor_id, "Second.")
    await _thread_checkpoint(client, project_id, t1, actor_id)
    await _thread_checkpoint(client, project_id, t2, actor_id)
    await _assign_model(session_factory, project_id)
    orch_id = await _start(session_factory, project_id, actor_id)

    async with session_factory() as session:
        result = await run_orchestration(session, orch_id, planner=_stub_planner(_one_calc()))

    assert result.max_passes == 1
    assert result.passes_commissioned == 1
    assert result.passes_skipped == 1
    assert result.stop_reason == STOP_MAX_PASSES
    skipped = next(d for d in result.decisions if d["action"] == "skipped")
    assert skipped["reason"] == "max_passes"
    assert skipped["thread_id"] == t2
