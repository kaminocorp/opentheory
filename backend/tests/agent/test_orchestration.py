"""The project-level multi-thread orchestrator (0.22.0) — DB-backed.

Drives ``run_orchestration`` with a **stub planner** so the loop is deterministic while
each commissioned ``run_agent_pass`` still goes through the real chokepoint. Covers
the release's acceptance matrix: budget stops the loop, multiple threads get passes,
empty/no-work exits cleanly, and a failed sub-pass does not corrupt the ledger
(no validation, no funding write, earlier checkpoints stand).
"""

import asyncio
import time
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
from app.services import compute as compute_service
from app.services import funding as funding_service
from app.services.compute import tokens_to_cost
from app.services.orchestration import (
    STOP_BUDGET_EXHAUSTED,
    STOP_CANCELLED,
    STOP_MAX_PASSES,
    STOP_NO_OPEN_WORK,
    request_cancel,
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
    project_id = await _project(client, "orch-empty", actor_id=actor_id)
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
    project_id = await _project(client, "orch-noclaim", actor_id=actor_id)
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
    project_id = await _project(client, "orch-closed", actor_id=actor_id)
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
    project_id = await _project(client, "orch-multi", actor_id=actor_id)
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
    project_id = await _project(client, "orch-budget", actor_id=actor_id)
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
    project_id = await _project(client, "orch-broke", actor_id=actor_id)
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
    project_id = await _project(client, "orch-fail", actor_id=actor_id)
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

    ok_stub = _stub_planner(_one_calc())

    async def _planner(
        thread, open_claims, catalog, model, *, llm, max_runs, grounding=None, observations=None
    ):
        if str(thread.id) == fail_id:
            raise AgentLlmError("planner failed on purpose")
        # One-shot: a raw PlanResult would replan the same calc until the pass cap.
        return await ok_stub(
            thread, open_claims, catalog, model, llm=llm, max_runs=max_runs,
            grounding=grounding, observations=observations,
        )

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
    project_id = await _project(client, "orch-cap", actor_id=actor_id)
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


def _sleeping_planner(*, hold: float, tokens_used: int = 10):
    """Record overlap so tests can prove concurrent vs sequential execution."""
    marks: dict[str, dict[str, float]] = {}

    async def _planner(
        thread, open_claims, catalog, model, *, llm, max_runs, grounding=None, observations=None
    ):
        tid = str(thread.id)
        marks[tid] = {"start": time.monotonic()}
        await asyncio.sleep(hold)
        marks[tid]["end"] = time.monotonic()
        if observations is None:
            return _one_calc(tokens_used=tokens_used)
        return PlanResult(runnable=[], proposed_count=0, tokens_used=0)

    return _planner, marks


def _waves_overlapped(marks: dict[str, dict[str, float]]) -> bool:
    starts = [row["start"] for row in marks.values()]
    ends = [row["end"] for row in marks.values()]
    return max(starts) < min(ends)


async def test_concurrent_subpasses_overlap_and_trace_the_wave(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "orchestration_concurrency", 2)
    actor_id = await _actor(client)
    project_id = await _project(client, "orch-parallel", actor_id=actor_id)
    t1 = await _thread(client, project_id, actor_id)
    t2 = await _thread(client, project_id, actor_id)
    await _claim(client, t1, actor_id, "First thread claim.")
    await _claim(client, t2, actor_id, "Second thread claim.")
    await _thread_checkpoint(client, project_id, t1, actor_id)
    await _thread_checkpoint(client, project_id, t2, actor_id)
    await _assign_model(session_factory, project_id)
    orch_id = await _start(session_factory, project_id, actor_id)
    planner, marks = _sleeping_planner(hold=0.2)

    async with session_factory() as session:
        result = await run_orchestration(session, orch_id, planner=planner)

    assert result.status is OrchestrationRunStatus.COMPLETED
    assert result.concurrency == 2
    assert result.passes_commissioned == 2
    assert result.passes_completed == 2
    assert _waves_overlapped(marks)
    commissioned = [d for d in result.decisions if d["action"] == "commissioned"]
    assert {d["thread_id"] for d in commissioned} == {t1, t2}
    assert all(d["wave"] == 1 for d in commissioned)
    assert all(d["parallel_with"] for d in commissioned)
    assert {d["parallel_with"][0] for d in commissioned} == {t1, t2}


async def test_concurrency_one_is_sequential(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "orchestration_concurrency", 1)
    actor_id = await _actor(client)
    project_id = await _project(client, "orch-seq", actor_id=actor_id)
    t1 = await _thread(client, project_id, actor_id)
    t2 = await _thread(client, project_id, actor_id)
    await _claim(client, t1, actor_id, "First.")
    await _claim(client, t2, actor_id, "Second.")
    await _thread_checkpoint(client, project_id, t1, actor_id)
    await _thread_checkpoint(client, project_id, t2, actor_id)
    await _assign_model(session_factory, project_id)
    orch_id = await _start(session_factory, project_id, actor_id)
    planner, marks = _sleeping_planner(hold=0.08)

    async with session_factory() as session:
        result = await run_orchestration(session, orch_id, planner=planner)

    assert result.concurrency == 1
    assert result.passes_completed == 2
    assert not _waves_overlapped(marks)
    commissioned = [d for d in result.decisions if d["action"] == "commissioned"]
    assert all(d["wave"] in (1, 2) for d in commissioned)
    assert all(d["parallel_with"] == [] for d in commissioned)


async def test_cancel_skips_remaining_threads_after_the_current_wave(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "orchestration_concurrency", 2)
    actor_id = await _actor(client)
    project_id = await _project(client, "orch-cancel", actor_id=actor_id)
    t1 = await _thread(client, project_id, actor_id)
    t2 = await _thread(client, project_id, actor_id)
    t3 = await _thread(client, project_id, actor_id)
    await _claim(client, t1, actor_id, "One.")
    await _claim(client, t2, actor_id, "Two.")
    await _claim(client, t3, actor_id, "Three.")
    await _thread_checkpoint(client, project_id, t1, actor_id)
    await _thread_checkpoint(client, project_id, t2, actor_id)
    await _thread_checkpoint(client, project_id, t3, actor_id)
    await _assign_model(session_factory, project_id)
    orch_id = await _start(session_factory, project_id, actor_id)

    started = asyncio.Event()

    async def _planner(
        thread, open_claims, catalog, model, *, llm, max_runs, grounding=None, observations=None
    ):
        started.set()
        await asyncio.sleep(0.2)
        if observations is None:
            return _one_calc()
        return PlanResult(runnable=[], proposed_count=0, tokens_used=0)

    async def _run() -> None:
        async with session_factory() as session:
            return await run_orchestration(session, orch_id, planner=_planner)

    task = asyncio.create_task(_run())
    await asyncio.wait_for(started.wait(), timeout=5)
    async with session_factory() as session:
        cancelled = await request_cancel(session, orch_id)
        assert cancelled.cancel_requested is True
    result = await asyncio.wait_for(task, timeout=10)

    assert result.status is OrchestrationRunStatus.COMPLETED
    assert result.stop_reason == STOP_CANCELLED
    assert result.passes_commissioned == 2
    assert result.passes_skipped == 1
    skipped = [d for d in result.decisions if d["action"] == "skipped"]
    assert skipped[0]["thread_id"] == t3
    assert skipped[0]["reason"] == "cancelled"


async def test_concurrent_reserve_cannot_oversell(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two sessions racing the last dollar: only one hold lands; available stays non-negative."""
    monkeypatch.setattr(settings, "agent_token_rate_usd_per_1k", Decimal("1.00"))
    monkeypatch.setattr(settings, "agent_pass_max_tokens", 1000)
    actor_id = await _actor(client)
    project_id = await _project(client, "orch-race", actor_id=actor_id)
    t1 = await _thread(client, project_id, actor_id)
    t2 = await _thread(client, project_id, actor_id)
    await _assign_model(session_factory, project_id, budget=None)
    await _grant_budget(session_factory, project_id, amount="1.00")

    from app.models.actor import Actor
    from app.services.agent_runs import start_agent_pass

    async with session_factory() as session:
        actor = await session.get(Actor, UUID(actor_id))
        a = await start_agent_pass(
            session, UUID(project_id), UUID(t1), triggered_by=actor, role="researcher"
        )
        b = await start_agent_pass(
            session, UUID(project_id), UUID(t2), triggered_by=actor, role="researcher"
        )
        a_id, b_id = a.id, b.id

    async def _reserve(run_id: UUID) -> Decimal | None:
        async with session_factory() as session:
            row = await session.get(AgentRun, run_id)
            held = await compute_service.reserve_compute_for_pass(
                session, row, rate_per_1k=Decimal("1.00")
            )
            await session.commit()
            return held

    held_a, held_b = await asyncio.gather(_reserve(a_id), _reserve(b_id))
    winners = [amount for amount in (held_a, held_b) if amount is not None]
    assert len(winners) == 1
    assert winners[0] == Decimal("1.000000")

    async with session_factory() as session:
        budget = await funding_service.project_budget(session, UUID(project_id))
        assert budget.reserved == Decimal("1.000000")
        assert budget.available == Decimal("0")
        assert budget.available >= 0
        assert budget.spent + budget.reserved <= budget.funded
