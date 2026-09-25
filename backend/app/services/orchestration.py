"""Thin multi-thread orchestrator (0.22.0 / 0.27.0) — allocate project budget across sub-passes.

``run_orchestration`` is contributor infrastructure: it selects open threads with
raisable claims, commissions capped ``run_agent_pass`` calls against the shared
``ComputeDebit`` / project-budget ceiling, and stops when the pot is empty, no
raisable work remains, the per-orchestration pass cap is hit, or a member cancels.

It invents **no** ledger mechanics. Each sub-pass goes through the existing
``start_agent_pass`` → ``run_agent_pass`` path (plan → observe → replan, 0.20.0).
This file never writes a ``Validation`` or a ``FundingAllocation``.

0.27.0 runs up to ``orchestration_concurrency`` sub-passes at once (default 2;
``1`` is the sequential fallback). Before a pass starts, a short critical
section locks the project row and holds a slice of ``available`` on the
``AgentRun``. Debit stays after tokens; the hold cannot oversell the pot.
The ``BudgetPolicy`` seam is the reserved slice.

Optional merge/tag after a landed pass is a no-op hook here — `0.21.0`
merge/tag stay human/API operations. See :data:`after_pass_hook`.
"""

from __future__ import annotations

import asyncio
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
    ResearchCampaignStatus,
    ThreadStatus,
)
from app.models.orchestration_run import OrchestrationRun
from app.models.project import Project
from app.models.research_campaign import ResearchCampaign
from app.models.thread import Thread
from app.schemas.claim import SETTLED_HEADLINES, ClaimGrounding
from app.services import agent_runs as agent_run_service
from app.services import compute as compute_service
from app.services import funding as funding_service
from app.services.agent_actors import get_or_create_project_agent_actor
from app.services.agent_runs import PlannerFn
from app.services.compute import BUDGET_EXHAUSTED, ProjectBudgetPolicy
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
SKIP_CANCELLED = "cancelled"

STOP_BUDGET_EXHAUSTED = "budget_exhausted"
STOP_NO_OPEN_WORK = "no_open_work"
STOP_MAX_PASSES = "max_passes"
STOP_CANCELLED = "cancelled"
STOP_ERROR = "error"

# Safety clamp so a typo in ORCHESTRATION_CONCURRENCY cannot fan out a process.
ORCHESTRATION_CONCURRENCY_HARD_CAP = 8

# Optional hook after a landed sub-pass. v1 never self-merges and never
# self-validates; the hook is a no-op unless a test injects one.
AfterPassHook = Callable[[AsyncSession, OrchestrationRun, AgentRun], Awaitable[None]]


def claim_is_raisable(headline: str) -> bool:
    """A claim can still climb (or be refuted) — its evidence axis is not decided."""
    return headline not in SETTLED_HEADLINES


def resolve_concurrency(requested: int | None = None) -> int:
    """Clamp concurrency to ``[1, min(settings, hard cap)]``. ``1`` is sequential."""
    configured = max(1, int(settings.orchestration_concurrency))
    cap = min(configured, ORCHESTRATION_CONCURRENCY_HARD_CAP)
    if requested is None:
        return cap
    return min(max(1, int(requested)), cap)


def _decision(
    thread: Thread,
    *,
    action: str,
    reason: str | None,
    agent_run: AgentRun | None = None,
    budget_remaining: Decimal | None = None,
    wave: int | None = None,
    parallel_with: list[str] | None = None,
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
        "wave": wave,
        "parallel_with": list(parallel_with) if parallel_with is not None else [],
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
    for_campaign: bool = False,
) -> OrchestrationRun:
    """Mint the ``running`` trace in the request session. One in-flight loop per project.

    A second concurrent commission is ``409`` — two loops racing the shared pot is the
    failure mode 0.19.0 already named. A running continuous campaign also blocks a
    standalone orchestration (they share the pot); the campaign itself passes
    ``for_campaign=True`` so it can commission its own cycles. ``role`` validity is
    enforced upstream.
    """
    project = (
        await db.execute(select(Project).where(Project.id == project_id).with_for_update())
    ).scalar_one_or_none()
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

    if not for_campaign:
        running_campaign = await db.execute(
            select(ResearchCampaign.id).where(
                ResearchCampaign.project_id == project_id,
                ResearchCampaign.status == ResearchCampaignStatus.RUNNING,
            )
        )
        if running_campaign.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A continuous research campaign is already running on this project",
            )

    run = OrchestrationRun(
        project_id=project_id,
        triggered_by_actor_id=triggered_by.id,
        role=role,
        status=OrchestrationRunStatus.RUNNING,
        max_passes=settings.orchestration_max_passes,
        concurrency=resolve_concurrency(),
    )
    db.add(run)
    await db.commit()
    return run


async def request_cancel(db: AsyncSession, orchestration_id: UUID) -> OrchestrationRun:
    """Ask a running orchestration to stop after the current wave. Idempotent while running."""
    run = await db.get(OrchestrationRun, orchestration_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Orchestration not found")
    if run.status is not OrchestrationRunStatus.RUNNING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Orchestration is not running",
        )
    run.cancel_requested = True
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
    pending: list[ThreadEligibility] = []
    stop_reason: str | None = None
    hit_budget = False
    hit_cap = False
    cancelled = False
    run_id = run.id
    pass_planner = planner if planner is not None else default_plan

    async def _reload() -> OrchestrationRun:
        reloaded = await db.get(OrchestrationRun, run_id)
        if reloaded is None:  # pragma: no cover
            raise ValueError(f"OrchestrationRun {run_id} disappeared")
        # Refresh so a cancel committed from another session is visible between waves.
        await db.refresh(reloaded)
        return reloaded

    async def _skip_all(rows: list[ThreadEligibility], reason: str) -> None:
        nonlocal run
        run = await _reload()
        live = await funding_service.project_budget(db, run.project_id)
        run.budget_available_end = live.available
        for eligibility in rows:
            decisions.append(
                _decision(
                    eligibility.thread,
                    action="skipped",
                    reason=reason,
                    budget_remaining=live.available,
                )
            )
            run.passes_skipped += 1
        run.decisions = list(decisions)
        await db.commit()

    for eligibility in classified:
        if eligibility.eligible:
            pending.append(eligibility)
            continue
        decisions.append(
            _decision(eligibility.thread, action="skipped", reason=eligibility.skip_reason)
        )
        run.passes_skipped += 1
        run.decisions = list(decisions)
        await db.commit()

    if pending:
        # Mint the per-project agent Actor once so concurrent sub-passes do not
        # race ``uq_actors_one_agent_per_project`` on first use.
        await get_or_create_project_agent_actor(db, run.project_id)
        await db.commit()

    wave_n = 0
    while pending:
        run = await _reload()
        if run.cancel_requested:
            await _skip_all(pending, SKIP_CANCELLED)
            cancelled = True
            break
        if run.passes_commissioned >= run.max_passes:
            await _skip_all(pending, SKIP_MAX_PASSES)
            hit_cap = True
            break

        live = await funding_service.project_budget(db, run.project_id)
        run.budget_available_end = live.available
        await db.commit()
        if live.available <= 0:
            await _skip_all(pending, SKIP_BUDGET_EXHAUSTED)
            hit_budget = True
            break

        slots = min(run.concurrency, run.max_passes - run.passes_commissioned, len(pending))
        wave: list[tuple[ThreadEligibility, AgentRun]] = []
        leftover: list[ThreadEligibility] = []
        for index, eligibility in enumerate(pending):
            if len(wave) >= slots:
                leftover.extend(pending[index:])
                break
            commissioned = await _commission_reserved_pass(db, run, actor, eligibility.thread)
            if commissioned is None:
                leftover.extend(pending[index:])
                break
            wave.append((eligibility, commissioned))
            run = await _reload()
        pending = leftover

        if not wave:
            await _skip_all(pending, SKIP_BUDGET_EXHAUSTED)
            hit_budget = True
            break

        wave_n += 1
        wave_thread_ids = [str(eligibility.thread.id) for eligibility, _ in wave]
        finished_runs = await _run_wave(
            db,
            [started.id for _, started in wave],
            planner=pass_planner,
            llm=llm,
        )

        live = await funding_service.project_budget(db, run.project_id)
        remaining = live.available
        run = await _reload()
        run.budget_available_end = remaining
        hook = after_pass if after_pass is not None else after_pass_hook

        for (eligibility, _started), finished in zip(wave, finished_runs, strict=True):
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
            peer_ids = [tid for tid in wave_thread_ids if tid != str(eligibility.thread.id)]
            decisions.append(
                _decision(
                    eligibility.thread,
                    action="commissioned",
                    reason=reason,
                    agent_run=finished,
                    budget_remaining=remaining,
                    wave=wave_n,
                    parallel_with=peer_ids,
                )
            )
            logger.info(
                "orchestration_pass orchestration_id=%s thread_id=%s agent_run_id=%s "
                "status=%s wave=%s budget_remaining=%s",
                run.id,
                eligibility.thread.id,
                finished.id,
                finished.status.value,
                wave_n,
                remaining,
            )
            if hook is not None:
                local = await db.get(AgentRun, finished.id)
                if local is not None:
                    await hook(db, run, local)

        run.decisions = list(decisions)
        await db.commit()
        if remaining <= 0:
            hit_budget = True

    if cancelled:
        stop_reason = STOP_CANCELLED
    elif hit_budget:
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


def _policy_from_reservation(agent_run: AgentRun) -> ProjectBudgetPolicy | None:
    if agent_run.reserved_amount is None or agent_run.reserved_amount <= 0:
        return None
    return ProjectBudgetPolicy(
        Decimal(agent_run.reserved_amount),
        rate_per_1k=compute_service.rate_for_model(agent_run.model),
    )


async def _commission_reserved_pass(
    db: AsyncSession,
    run: OrchestrationRun,
    actor: Actor,
    thread: Thread,
) -> AgentRun | None:
    """Lock the project, hold a slice, mint the running pass. ``None`` if the pot is gone."""
    project = (
        await db.execute(select(Project).where(Project.id == run.project_id).with_for_update())
    ).scalar_one_or_none()
    if project is None:
        return None
    live = await funding_service.project_budget(db, run.project_id)
    if live.available <= 0:
        return None
    model = (project.agent_models or {}).get(run.role)
    rate = compute_service.rate_for_model(model)
    amount = compute_service.pass_reserve_amount(live.available, rate_per_1k=rate)
    if amount <= 0:
        return None
    agent_run = await agent_run_service.start_agent_pass(
        db, run.project_id, thread.id, triggered_by=actor, role=run.role, commit=False
    )
    agent_run.reserved_amount = amount
    live_run = await db.get(OrchestrationRun, run.id)
    if live_run is not None:
        live_run.passes_commissioned += 1
    await db.commit()
    return agent_run


async def _run_wave(
    db: AsyncSession,
    agent_run_ids: list[UUID],
    *,
    planner: PlannerFn,
    llm: Any | None,
) -> list[AgentRun]:
    """Run one wave. ``concurrency=1`` (or a singleton wave) stays on the caller session."""
    if len(agent_run_ids) == 1:
        row = await db.get(AgentRun, agent_run_ids[0])
        policy = _policy_from_reservation(row) if row is not None else None
        finished = await agent_run_service.run_agent_pass(
            db, agent_run_ids[0], llm=llm, planner=planner, budget_policy=policy
        )
        return [finished]

    # ``get_bind()`` is the sync Engine; concurrent tasks need the AsyncEngine.
    factory = async_sessionmaker(db.bind, expire_on_commit=False, class_=AsyncSession)

    async def _one(agent_run_id: UUID) -> AgentRun:
        async with factory() as session:
            row = await session.get(AgentRun, agent_run_id)
            policy = _policy_from_reservation(row) if row is not None else None
            return await agent_run_service.run_agent_pass(
                session, agent_run_id, llm=llm, planner=planner, budget_policy=policy
            )

    gathered = await asyncio.gather(
        *[_one(agent_run_id) for agent_run_id in agent_run_ids],
        return_exceptions=True,
    )
    finished: list[AgentRun] = []
    for agent_run_id, result in zip(agent_run_ids, gathered, strict=True):
        if isinstance(result, BaseException):
            logger.warning(
                "orchestration_wave_pass_error agent_run_id=%s error=%s",
                agent_run_id,
                result,
            )
            async with factory() as session:
                row = await session.get(AgentRun, agent_run_id)
                if row is not None and row.status is AgentRunStatus.RUNNING:
                    await compute_service.release_compute_reservation(session, row)
                    row.status = AgentRunStatus.FAILED
                    row.error = str(result)[:2000]
                    await session.commit()
                if row is None:  # pragma: no cover
                    raise result
                finished.append(row)
        else:
            finished.append(result)
    return finished


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
