"""Thin multi-thread orchestrator (0.22.0) — allocate project budget across sub-passes.

``run_orchestration`` is contributor infrastructure: it selects open threads with
raisable claims, commissions capped ``run_agent_pass`` calls against the shared
``ComputeDebit`` / project-budget ceiling, and stops when the pot is empty, no
raisable work remains, or the per-orchestration pass cap is hit.

It invents **no** ledger mechanics. Each sub-pass goes through the existing
``start_agent_pass`` → ``run_agent_pass`` path (plan → observe → replan, 0.20.0).
This file never writes a ``Validation`` or a ``FundingAllocation``.

v1 is **sequential**. Concurrent sub-passes would race ``project_budget.available``
(the same class of race 0.19.0 already records for concurrent first-passes). The
``BudgetPolicy`` seam stays on each sub-pass; this loop only decides *whether* to
commission the next one.

Optional merge/tag after a landed pass is a no-op hook here — `0.21.0`
merge/tag stay human/API operations. See :data:`after_pass_hook`.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.planner import plan as default_plan
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.actor import Actor
from app.models.agent_run import AgentRun
from app.models.claim import Claim
from app.models.enums import (
    AgentRunStatus,
    ClaimStatus,
    OrchestrationRunStatus,
    ThreadStatus,
)
from app.models.orchestration_run import OrchestrationRun
from app.models.project import Project
from app.models.thread import Thread
from app.schemas.claim import SETTLED_HEADLINES, ClaimGrounding
from app.services import agent_runs as agent_run_service
from app.services import funding as funding_service
from app.services.agent_runs import PlannerFn
from app.services.compute import BUDGET_EXHAUSTED
from app.services.grounding import grounding_by_claim

logger = logging.getLogger(__name__)

_SETTLED_CLAIM_STATUSES = (ClaimStatus.RETRACTED, ClaimStatus.VALIDATED)
_OPEN_THREAD_STATUSES = (ThreadStatus.OPEN, ThreadStatus.ACTIVE)

# Why a thread was not commissioned. Stable strings the trace and tests assert against.
SKIP_NO_OPEN_CLAIMS = "no_open_claims"
SKIP_NO_RAISABLE_CLAIMS = "no_raisable_claims"
SKIP_THREAD_NOT_OPEN = "thread_not_open"
SKIP_PASS_IN_FLIGHT = "pass_in_flight"
SKIP_BUDGET_EXHAUSTED = "budget_exhausted"
SKIP_MAX_PASSES = "max_passes"

STOP_BUDGET_EXHAUSTED = "budget_exhausted"
STOP_NO_OPEN_WORK = "no_open_work"
STOP_MAX_PASSES = "max_passes"
STOP_ERROR = "error"

# Optional hook after a landed sub-pass. v1 never self-merges and never
# self-validates; the hook is a no-op unless a test injects one.
AfterPassHook = Callable[[AsyncSession, OrchestrationRun, AgentRun], Awaitable[None]]


def claim_is_raisable(headline: str) -> bool:
    """A claim can still climb (or be refuted) — its evidence axis is not decided."""
    return headline not in SETTLED_HEADLINES


def _decision(
    thread: Thread,
    *,
    action: str,
    reason: str | None,
    agent_run: AgentRun | None = None,
    budget_remaining: Decimal | None = None,
) -> dict[str, Any]:
    return {
        "thread_id": str(thread.id),
        "thread_title": thread.title,
        "action": action,
        "reason": reason,
        "agent_run_id": str(agent_run.id) if agent_run is not None else None,
        "agent_run_status": agent_run.status.value if agent_run is not None else None,
        "tokens_used": agent_run.tokens_used if agent_run is not None else None,
        "ran_count": agent_run.ran_count if agent_run is not None else None,
        "budget_remaining": str(budget_remaining) if budget_remaining is not None else None,
    }


async def _open_claims(db: AsyncSession, thread_id: UUID) -> list[Claim]:
    result = await db.execute(
        select(Claim)
        .where(
            Claim.thread_id == thread_id,
            Claim.status.notin_(_SETTLED_CLAIM_STATUSES),
        )
        .order_by(Claim.created_at)
    )
    return list(result.scalars())


async def _thread_has_running_pass(db: AsyncSession, thread_id: UUID) -> bool:
    result = await db.execute(
        select(AgentRun.id)
        .where(AgentRun.thread_id == thread_id, AgentRun.status == AgentRunStatus.RUNNING)
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


@dataclass
class ThreadEligibility:
    """Why a thread would be commissioned or skipped — computed before any pass runs."""

    thread: Thread
    skip_reason: str | None
    raisable_count: int = 0

    @property
    def eligible(self) -> bool:
        return self.skip_reason is None


async def classify_thread(db: AsyncSession, thread: Thread) -> ThreadEligibility:
    """Decide whether this thread is open work the orchestrator should spend against.

    Order of reasons (first match wins): thread not open → a pass already in flight
    → no open claims → every remaining open claim is settled on the evidence axis.
    """
    if thread.status not in _OPEN_THREAD_STATUSES:
        return ThreadEligibility(thread, SKIP_THREAD_NOT_OPEN)
    if await _thread_has_running_pass(db, thread.id):
        return ThreadEligibility(thread, SKIP_PASS_IN_FLIGHT)
    open_claims = await _open_claims(db, thread.id)
    if not open_claims:
        return ThreadEligibility(thread, SKIP_NO_OPEN_CLAIMS)
    grounding = await grounding_by_claim(db, [claim.id for claim in open_claims])
    empty = ClaimGrounding()
    raisable = sum(
        1
        for claim in open_claims
        if claim_is_raisable((grounding.get(claim.id) or empty).headline)
    )
    if raisable == 0:
        return ThreadEligibility(thread, SKIP_NO_RAISABLE_CLAIMS, raisable_count=0)
    return ThreadEligibility(thread, None, raisable_count=raisable)


async def classify_project_threads(db: AsyncSession, project_id: UUID) -> list[ThreadEligibility]:
    """Oldest-first classification of every thread on the project."""
    rows = list(
        (
            await db.execute(
                select(Thread).where(Thread.project_id == project_id).order_by(Thread.created_at)
            )
        ).scalars()
    )
    return [await classify_thread(db, thread) for thread in rows]


async def _finalize(
    db: AsyncSession,
    run: OrchestrationRun,
    *,
    status: OrchestrationRunStatus,
    stop_reason: str | None,
    error: str | None = None,
    budget_end: Decimal | None = None,
) -> OrchestrationRun:
    run.status = status
    run.stop_reason = stop_reason
    if error is not None:
        run.error = error[:2000]
    if budget_end is not None:
        run.budget_available_end = budget_end
    await db.commit()
    return run


async def start_orchestration(
    db: AsyncSession,
    project_id: UUID,
    *,
    triggered_by: Actor,
    role: str,
) -> OrchestrationRun:
    """Mint the ``running`` trace in the request session. One in-flight loop per project.

    A second concurrent commission is ``409`` — two loops racing the shared pot is the
    failure mode 0.19.0 already named. ``role`` validity is enforced upstream.
    """
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    existing = await db.execute(
        select(OrchestrationRun)
        .where(
            OrchestrationRun.project_id == project_id,
            OrchestrationRun.status == OrchestrationRunStatus.RUNNING,
        )
        .with_for_update()
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An orchestration is already running on this project",
        )

    run = OrchestrationRun(
        project_id=project_id,
        triggered_by_actor_id=triggered_by.id,
        role=role,
        status=OrchestrationRunStatus.RUNNING,
        max_passes=settings.orchestration_max_passes,
    )
    db.add(run)
    await db.commit()
    return run


async def run_orchestration(
    db: AsyncSession,
    orchestration_id: UUID,
    *,
    planner: PlannerFn | None = None,
    llm: Any | None = None,
    after_pass: AfterPassHook | None = None,
) -> OrchestrationRun:
    """Execute the orchestration identified by ``orchestration_id``.

    Any unexpected failure is recorded as ``status=failed`` (never a dangling
    ``running`` row). A failed *sub-pass* does not fail the loop: it is a decision
    row, and the next eligible thread is still considered.
    """
    run = await db.get(OrchestrationRun, orchestration_id)
    if run is None:
        raise ValueError(f"OrchestrationRun {orchestration_id} not found")

    try:
        return await _execute(db, run, planner=planner, llm=llm, after_pass=after_pass)
    except Exception as exc:
        logger.warning(
            "orchestration_unexpected_error orchestration_id=%s error=%s",
            orchestration_id,
            exc,
        )
        await db.rollback()
        reloaded = await db.get(OrchestrationRun, orchestration_id)
        if reloaded is None:  # pragma: no cover
            raise
        return await _finalize(
            db,
            reloaded,
            status=OrchestrationRunStatus.FAILED,
            stop_reason=STOP_ERROR,
            error=str(exc),
        )


async def _execute(
    db: AsyncSession,
    run: OrchestrationRun,
    *,
    planner: PlannerFn | None,
    llm: Any | None,
    after_pass: AfterPassHook | None,
) -> OrchestrationRun:
    actor = await db.get(Actor, run.triggered_by_actor_id)
    if actor is None:
        return await _finalize(
            db,
            run,
            status=OrchestrationRunStatus.FAILED,
            stop_reason=STOP_ERROR,
            error="triggering actor not found",
        )

    opening = await funding_service.project_budget(db, run.project_id)
    run.budget_available_start = opening.available
    run.budget_available_end = opening.available
    decisions: list[dict[str, Any]] = []
    run.decisions = list(decisions)
    await db.commit()

    classified = await classify_project_threads(db, run.project_id)
    remaining = opening.available
    stop_reason: str | None = None
    hit_budget = False
    hit_cap = False
    run_id = run.id

    async def _reload() -> OrchestrationRun:
        reloaded = await db.get(OrchestrationRun, run_id)
        if reloaded is None:  # pragma: no cover
            raise ValueError(f"OrchestrationRun {run_id} disappeared")
        return reloaded

    for eligibility in classified:
        thread = eligibility.thread
        run = await _reload()
        if not eligibility.eligible:
            decisions.append(_decision(thread, action="skipped", reason=eligibility.skip_reason))
            run.passes_skipped += 1
            run.decisions = list(decisions)
            await db.commit()
            continue

        if run.passes_commissioned >= run.max_passes:
            decisions.append(_decision(thread, action="skipped", reason=SKIP_MAX_PASSES))
            run.passes_skipped += 1
            run.decisions = list(decisions)
            await db.commit()
            hit_cap = True
            continue

        live = await funding_service.project_budget(db, run.project_id)
        remaining = live.available
        run.budget_available_end = remaining
        if remaining <= 0:
            decisions.append(
                _decision(
                    thread,
                    action="skipped",
                    reason=SKIP_BUDGET_EXHAUSTED,
                    budget_remaining=remaining,
                )
            )
            run.passes_skipped += 1
            run.decisions = list(decisions)
            await db.commit()
            hit_budget = True
            continue

        agent_run = await agent_run_service.start_agent_pass(
            db, run.project_id, thread.id, triggered_by=actor, role=run.role
        )
        run = await _reload()
        run.passes_commissioned += 1
        run.decisions = list(decisions)
        await db.commit()

        pass_planner = planner if planner is not None else default_plan
        finished = await agent_run_service.run_agent_pass(
            db, agent_run.id, llm=llm, planner=pass_planner
        )
        live = await funding_service.project_budget(db, run.project_id)
        remaining = live.available
        run = await _reload()
        run.budget_available_end = remaining

        if finished.status is AgentRunStatus.COMPLETED:
            run.passes_completed += 1
            reason = "completed"
        else:
            run.passes_failed += 1
            reason = (
                SKIP_BUDGET_EXHAUSTED
                if finished.error == BUDGET_EXHAUSTED
                else (finished.error or "failed")
            )
            if finished.error == BUDGET_EXHAUSTED:
                hit_budget = True

        decisions.append(
            _decision(
                thread,
                action="commissioned",
                reason=reason,
                agent_run=finished,
                budget_remaining=remaining,
            )
        )
        run.decisions = list(decisions)
        await db.commit()
        logger.info(
            "orchestration_pass orchestration_id=%s thread_id=%s agent_run_id=%s "
            "status=%s budget_remaining=%s",
            run.id,
            thread.id,
            finished.id,
            finished.status.value,
            remaining,
        )

        hook = after_pass if after_pass is not None else after_pass_hook
        if hook is not None:
            await hook(db, run, finished)

        if remaining <= 0:
            hit_budget = True

    if hit_budget:
        stop_reason = STOP_BUDGET_EXHAUSTED
    elif hit_cap:
        stop_reason = STOP_MAX_PASSES
    else:
        stop_reason = STOP_NO_OPEN_WORK

    final = await funding_service.project_budget(db, run.project_id)
    return await _finalize(
        db,
        run,
        status=OrchestrationRunStatus.COMPLETED,
        stop_reason=stop_reason,
        budget_end=final.available,
    )


@dataclass
class OrchestrationExecutor:
    """The seam :func:`run_orchestration_background` resolves at call time.

    Same shape as ``agent_runs.BackgroundExecutor``: production keeps the app engine
    and the real planner; a DB-backed route test rebinds this one object so the
    background loop runs against the test engine with a stub planner.
    """

    session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal
    planner: PlannerFn = agent_run_service.default_plan
    llm: Any | None = None
    after_pass: AfterPassHook | None = None


background_executor = OrchestrationExecutor()

# Production no-op. A later merge/tag hook can replace this; v1 must not
# self-merge or self-validate.
after_pass_hook: AfterPassHook | None = None


async def run_orchestration_background(orchestration_id: UUID) -> None:
    """FastAPI ``BackgroundTask`` entrypoint: run the loop in a fresh session."""
    executor = background_executor
    try:
        async with executor.session_factory() as db:
            await run_orchestration(
                db,
                orchestration_id,
                planner=executor.planner,
                llm=executor.llm,
                after_pass=executor.after_pass,
            )
        return
    except Exception:
        logger.exception("orchestration_background_crashed orchestration_id=%s", orchestration_id)

    try:
        async with executor.session_factory() as db:
            run = await db.get(OrchestrationRun, orchestration_id)
            if run is not None and run.status is OrchestrationRunStatus.RUNNING:
                run.status = OrchestrationRunStatus.FAILED
                run.stop_reason = STOP_ERROR
                run.error = "background orchestration crashed unexpectedly"
                await db.commit()
    except Exception:
        logger.exception(
            "orchestration_background_finalize_failed orchestration_id=%s", orchestration_id
        )


_STALE_RUN_MARGIN_S = 30.0


def _stale_running_cutoff() -> datetime:
    """Worst-case wall-clock for a legitimate orchestration + a margin."""
    per_pass = (
        settings.agent_llm_timeout_s * (1 + settings.agent_pass_max_replans)
        + settings.agent_pass_max_runs * settings.toolbench_wall_timeout_s
    )
    ttl = settings.orchestration_max_passes * per_pass + _STALE_RUN_MARGIN_S
    return datetime.now(UTC) - timedelta(seconds=ttl)


def _sweep_if_stale(run: OrchestrationRun, cutoff: datetime) -> bool:
    if run.status is OrchestrationRunStatus.RUNNING and run.updated_at < cutoff:
        run.status = OrchestrationRunStatus.FAILED
        run.stop_reason = STOP_ERROR
        run.error = "lost — the background worker did not finish (stale run swept on read)"
        return True
    return False


async def list_project_orchestrations(db: AsyncSession, project_id: UUID) -> list[OrchestrationRun]:
    """Newest-first traces for a project, sweeping any stale ``running`` rows first."""
    rows = list(
        (
            await db.execute(
                select(OrchestrationRun)
                .where(OrchestrationRun.project_id == project_id)
                .order_by(OrchestrationRun.created_at.desc())
            )
        ).scalars()
    )
    cutoff = _stale_running_cutoff()
    swept = [_sweep_if_stale(row, cutoff) for row in rows]
    if any(swept):
        await db.commit()
    return rows


async def get_orchestration(db: AsyncSession, orchestration_id: UUID) -> OrchestrationRun:
    run = await db.get(OrchestrationRun, orchestration_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Orchestration not found"
        )
    if _sweep_if_stale(run, _stale_running_cutoff()):
        await db.commit()
    return run
