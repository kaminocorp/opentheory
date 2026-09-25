"""Continuous research campaign (0.25.0 / 0.32.0) — re-commission the orchestrator.

``run_campaign`` is contributor infrastructure: it repeatedly commissions
``start_orchestration`` → ``run_orchestration`` against the shared
``ComputeDebit`` / project-budget ceiling, and stops when the pot is empty, no
raisable work remains, the cycle cap is hit, the human cancels, or consecutive
cycle failures exhaust the error budget.

It invents **no** ledger mechanics and never writes a ``Validation`` or a
``FundingAllocation``. Merge / tag stay human/API operations — this loop does
not call ``services/merges.py``.

One in-flight campaign per project; a running campaign also blocks a standalone
orchestration (they share the pot). Each cycle is one 0.22.0 / 0.27.0
orchestration, so per-orchestration ``orchestration_max_passes`` and
``orchestration_concurrency`` still bound a single scan; the campaign is what
continues after that cap.

``0.32.0`` may run a bounded number of those cycles at once
(``campaign_cycle_concurrency``, default ``1`` = sequential). Concurrent cycle
starts serialize on the same project-row reservation lock as ``0.27.0``
sub-passes, so they cannot oversell the pot. Live OpenRouter quotes (``0.28.0``)
remain the source for hold + debit. ``1`` stays on the caller session; ``>1``
runs peer orchestrations on their own sessions, like a ``0.27.0`` wave.
"""

from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.actor import Actor
from app.models.enums import OrchestrationRunStatus, ResearchCampaignStatus
from app.models.orchestration_run import OrchestrationRun
from app.models.project import Project
from app.models.research_campaign import ResearchCampaign
from app.services import agent_runs as agent_run_service
from app.services import funding as funding_service
from app.services import orchestration as orchestration_service
from app.services.agent_actors import get_or_create_project_agent_actor
from app.services.agent_runs import PlannerFn
from app.services.orchestration import (
    STOP_BUDGET_EXHAUSTED,
    STOP_ERROR,
    STOP_NO_OPEN_WORK,
    classify_project_threads,
)
from app.services.orchestration import (
    STOP_CANCELLED as ORCH_STOP_CANCELLED,
)
from app.services.orchestration import (
    STOP_MAX_PASSES as ORCH_STOP_MAX_PASSES,
)

logger = logging.getLogger(__name__)

STOP_MAX_CYCLES = "max_cycles"
STOP_CANCELLED = "cancelled"
STOP_ERROR_BUDGET = "error_budget"
STOP_CAMPAIGN_ERROR = "error"

# Safety clamp so a typo in CAMPAIGN_CYCLE_CONCURRENCY cannot fan out a process.
CAMPAIGN_CYCLE_CONCURRENCY_HARD_CAP = 4


def resolve_max_cycles(requested: int | None) -> int:
    """Clamp a client-supplied cap to the server safety bound (never above settings)."""
    cap = settings.campaign_max_cycles
    if requested is None:
        return cap
    return min(max(1, requested), cap)


def resolve_cycle_concurrency(requested: int | None = None) -> int:
    """Clamp cycle concurrency to ``[1, min(settings, hard cap)]``. ``1`` is sequential."""
    configured = max(1, int(settings.campaign_cycle_concurrency))
    cap = min(configured, CAMPAIGN_CYCLE_CONCURRENCY_HARD_CAP)
    if requested is None:
        return cap
    return min(max(1, int(requested)), cap)


def _cycle_slots(campaign: ResearchCampaign, eligible_count: int) -> int:
    """How many cycles this wave should start.

    A single orchestration can cover ``orchestration_max_passes`` threads, so a
    second cycle is only useful when leftover work would otherwise wait for the
    next sequential scan. ``concurrency=1`` is always one cycle per wave.
    """
    remaining = campaign.max_cycles - campaign.current_cycle
    if remaining <= 0 or eligible_count <= 0:
        return 0
    per_scan = max(1, int(settings.orchestration_max_passes))
    needed = max(1, math.ceil(eligible_count / per_scan))
    return min(campaign.concurrency, remaining, needed)


async def _lock_project(db: AsyncSession, project_id: UUID) -> Project:
    project = (
        await db.execute(select(Project).where(Project.id == project_id).with_for_update())
    ).scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


async def project_has_running_campaign(db: AsyncSession, project_id: UUID) -> bool:
    result = await db.execute(
        select(ResearchCampaign.id).where(
            ResearchCampaign.project_id == project_id,
            ResearchCampaign.status == ResearchCampaignStatus.RUNNING,
        )
    )
    return result.scalar_one_or_none() is not None


async def project_has_running_orchestration(db: AsyncSession, project_id: UUID) -> bool:
    result = await db.execute(
        select(OrchestrationRun.id).where(
            OrchestrationRun.project_id == project_id,
            OrchestrationRun.status == OrchestrationRunStatus.RUNNING,
        )
    )
    return result.scalar_one_or_none() is not None


def _cycle_row(
    cycle: int,
    orch: OrchestrationRun | None,
    *,
    budget_remaining: Decimal | None,
    error: str | None = None,
    wave: int | None = None,
    parallel_with: list[int] | None = None,
) -> dict[str, Any]:
    return {
        "cycle": cycle,
        "orchestration_id": str(orch.id) if orch is not None else None,
        "orchestration_status": orch.status.value if orch is not None else None,
        "stop_reason": orch.stop_reason if orch is not None else None,
        "passes_commissioned": orch.passes_commissioned if orch is not None else None,
        "passes_completed": orch.passes_completed if orch is not None else None,
        "passes_failed": orch.passes_failed if orch is not None else None,
        "budget_remaining": str(budget_remaining) if budget_remaining is not None else None,
        "error": error,
        "wave": wave,
        "parallel_with": list(parallel_with) if parallel_with is not None else [],
    }


async def _finalize(
    db: AsyncSession,
    campaign: ResearchCampaign,
    *,
    status: ResearchCampaignStatus,
    stop_reason: str | None,
    error: str | None = None,
    budget_end: Decimal | None = None,
) -> ResearchCampaign:
    campaign.status = status
    campaign.stop_reason = stop_reason
    if error is not None:
        campaign.error = error[:2000]
    if budget_end is not None:
        campaign.budget_available_end = budget_end
    await db.commit()
    return campaign


async def start_campaign(
    db: AsyncSession,
    project_id: UUID,
    *,
    triggered_by: Actor,
    role: str,
    max_cycles: int | None = None,
) -> ResearchCampaign:
    """Mint the ``running`` campaign. One in-flight campaign (or orchestration) per project."""
    await _lock_project(db, project_id)

    if await project_has_running_campaign(db, project_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A continuous research campaign is already running on this project",
        )
    if await project_has_running_orchestration(db, project_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An orchestration is already running on this project",
        )

    campaign = ResearchCampaign(
        project_id=project_id,
        triggered_by_actor_id=triggered_by.id,
        role=role,
        status=ResearchCampaignStatus.RUNNING,
        max_cycles=resolve_max_cycles(max_cycles),
        error_budget=settings.campaign_error_budget,
        concurrency=resolve_cycle_concurrency(),
    )
    db.add(campaign)
    await db.commit()
    return campaign


async def _running_orchestrations(
    db: AsyncSession, project_id: UUID
) -> list[OrchestrationRun]:
    return list(
        (
            await db.execute(
                select(OrchestrationRun).where(
                    OrchestrationRun.project_id == project_id,
                    OrchestrationRun.status == OrchestrationRunStatus.RUNNING,
                )
            )
        ).scalars()
    )


async def request_cancel(db: AsyncSession, campaign_id: UUID) -> ResearchCampaign:
    """Ask a running campaign to stop after the current wave. Idempotent while running."""
    campaign = await db.get(ResearchCampaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    if campaign.status is not ResearchCampaignStatus.RUNNING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Campaign is not running",
        )
    campaign.cancel_requested = True
    for running_orch in await _running_orchestrations(db, campaign.project_id):
        running_orch.cancel_requested = True
    await db.commit()
    return campaign


async def run_campaign(
    db: AsyncSession,
    campaign_id: UUID,
    *,
    planner: PlannerFn | None = None,
    llm: Any | None = None,
) -> ResearchCampaign:
    """Execute the campaign identified by ``campaign_id``.

    Any unexpected outer failure is recorded as ``status=failed`` (never a dangling
    ``running`` row). A failed *cycle* increments the error budget; the next cycle
    still runs unless that budget is exhausted.
    """
    campaign = await db.get(ResearchCampaign, campaign_id)
    if campaign is None:
        raise ValueError(f"ResearchCampaign {campaign_id} not found")

    try:
        return await _execute(db, campaign, planner=planner, llm=llm)
    except Exception as exc:
        logger.warning(
            "campaign_unexpected_error campaign_id=%s error=%s",
            campaign_id,
            exc,
        )
        await db.rollback()
        reloaded = await db.get(ResearchCampaign, campaign_id)
        if reloaded is None:  # pragma: no cover
            raise
        return await _finalize(
            db,
            reloaded,
            status=ResearchCampaignStatus.FAILED,
            stop_reason=STOP_CAMPAIGN_ERROR,
            error=str(exc),
        )


async def _fail_running_orchestration(
    db: AsyncSession, orchestration_id: UUID, error: str
) -> OrchestrationRun | None:
    leftover = await db.get(OrchestrationRun, orchestration_id)
    if leftover is not None and leftover.status is OrchestrationRunStatus.RUNNING:
        leftover.status = OrchestrationRunStatus.FAILED
        leftover.stop_reason = STOP_ERROR
        leftover.error = error[:2000]
        await db.commit()
    return leftover


async def _run_cycle_wave(
    db: AsyncSession,
    orchestration_ids: list[UUID],
    *,
    planner: PlannerFn | None,
    llm: Any | None,
) -> list[OrchestrationRun | BaseException]:
    """Run one wave of cycles. ``concurrency=1`` stays on the caller session."""
    if len(orchestration_ids) == 1:
        try:
            finished = await orchestration_service.run_orchestration(
                db, orchestration_ids[0], planner=planner, llm=llm
            )
            return [finished]
        except Exception as exc:
            await db.rollback()
            await _fail_running_orchestration(db, orchestration_ids[0], str(exc))
            return [exc]

    factory = async_sessionmaker(db.bind, expire_on_commit=False, class_=AsyncSession)

    async def _one(orchestration_id: UUID) -> OrchestrationRun:
        async with factory() as session:
            return await orchestration_service.run_orchestration(
                session, orchestration_id, planner=planner, llm=llm
            )

    gathered = await asyncio.gather(
        *[_one(orchestration_id) for orchestration_id in orchestration_ids],
        return_exceptions=True,
    )
    finished: list[OrchestrationRun | BaseException] = []
    for orchestration_id, result in zip(orchestration_ids, gathered, strict=True):
        if isinstance(result, BaseException):
            logger.warning(
                "campaign_wave_cycle_error orchestration_id=%s error=%s",
                orchestration_id,
                result,
            )
            async with factory() as session:
                await _fail_running_orchestration(session, orchestration_id, str(result))
            finished.append(result)
        else:
            finished.append(result)
    return finished


@dataclass
class _WaveCycle:
    number: int
    orchestration_id: UUID | None
    error: str | None = None


async def _execute(
    db: AsyncSession,
    campaign: ResearchCampaign,
    *,
    planner: PlannerFn | None,
    llm: Any | None,
) -> ResearchCampaign:
    actor = await db.get(Actor, campaign.triggered_by_actor_id)
    if actor is None:
        return await _finalize(
            db,
            campaign,
            status=ResearchCampaignStatus.FAILED,
            stop_reason=STOP_CAMPAIGN_ERROR,
            error="triggering actor not found",
        )

    opening = await funding_service.project_budget(db, campaign.project_id)
    if campaign.budget_available_start is None:
        campaign.budget_available_start = opening.available
    campaign.budget_available_end = opening.available
    await db.commit()

    campaign_id = campaign.id

    async def _reload() -> ResearchCampaign:
        reloaded = await db.get(ResearchCampaign, campaign_id)
        if reloaded is None:  # pragma: no cover
            raise ValueError(f"ResearchCampaign {campaign_id} disappeared")
        # Refresh so a cancel committed from another session (the Stop route)
        # is visible between waves — ``get`` would otherwise return the
        # identity-map copy.
        await db.refresh(reloaded)
        return reloaded

    wave_n = 0
    while True:
        campaign = await _reload()
        if campaign.cancel_requested:
            final = await funding_service.project_budget(db, campaign.project_id)
            return await _finalize(
                db,
                campaign,
                status=ResearchCampaignStatus.COMPLETED,
                stop_reason=STOP_CANCELLED,
                budget_end=final.available,
            )

        if campaign.current_cycle >= campaign.max_cycles:
            final = await funding_service.project_budget(db, campaign.project_id)
            return await _finalize(
                db,
                campaign,
                status=ResearchCampaignStatus.COMPLETED,
                stop_reason=STOP_MAX_CYCLES,
                budget_end=final.available,
            )

        live = await funding_service.project_budget(db, campaign.project_id)
        campaign.budget_available_end = live.available

        classified = await classify_project_threads(db, campaign.project_id)
        eligible_count = sum(1 for row in classified if row.eligible)
        if eligible_count == 0:
            await db.commit()
            return await _finalize(
                db,
                campaign,
                status=ResearchCampaignStatus.COMPLETED,
                stop_reason=STOP_NO_OPEN_WORK,
                budget_end=live.available,
            )

        if live.available <= 0:
            await db.commit()
            return await _finalize(
                db,
                campaign,
                status=ResearchCampaignStatus.COMPLETED,
                stop_reason=STOP_BUDGET_EXHAUSTED,
                budget_end=live.available,
            )

        slots = _cycle_slots(campaign, eligible_count)
        if slots < 1:
            await db.commit()
            return await _finalize(
                db,
                campaign,
                status=ResearchCampaignStatus.COMPLETED,
                stop_reason=STOP_MAX_CYCLES,
                budget_end=live.available,
            )

        # Mint the per-project agent Actor once so concurrent cycles do not
        # race ``uq_actors_one_agent_per_project`` on first use (same reason
        # 0.27.0 mints it before a sub-pass wave).
        await get_or_create_project_agent_actor(db, campaign.project_id)
        await db.commit()

        wave_n += 1
        actor = await db.get(Actor, campaign.triggered_by_actor_id)
        if actor is None:
            return await _finalize(
                db,
                campaign,
                status=ResearchCampaignStatus.FAILED,
                stop_reason=STOP_CAMPAIGN_ERROR,
                error="triggering actor not found",
            )

        planned: list[_WaveCycle] = []
        for _ in range(slots):
            campaign = await _reload()
            if campaign.cancel_requested or campaign.current_cycle >= campaign.max_cycles:
                break
            campaign.current_cycle += 1
            cycle_n = campaign.current_cycle
            await db.commit()
            try:
                orch = await orchestration_service.start_orchestration(
                    db,
                    campaign.project_id,
                    triggered_by=actor,
                    role=campaign.role,
                    for_campaign=True,
                )
                planned.append(_WaveCycle(cycle_n, orch.id))
            except Exception as exc:
                logger.warning(
                    "campaign_cycle_start_error campaign_id=%s cycle=%s error=%s",
                    campaign_id,
                    cycle_n,
                    exc,
                )
                planned.append(_WaveCycle(cycle_n, None, error=str(exc)))

        started_ids = [row.orchestration_id for row in planned if row.orchestration_id is not None]
        wave_results: dict[UUID, OrchestrationRun | BaseException] = {}
        if started_ids:
            finished_rows = await _run_cycle_wave(
                db, started_ids, planner=planner, llm=llm
            )
            for orch_id, result in zip(started_ids, finished_rows, strict=True):
                wave_results[orch_id] = result

        live = await funding_service.project_budget(db, campaign.project_id)
        campaign = await _reload()
        campaign.budget_available_end = live.available
        cycles = list(campaign.cycles)
        peer_nums = [row.number for row in planned]
        recorded: list[dict[str, Any]] = []

        for row in planned:
            peers = [n for n in peer_nums if n != row.number]
            if row.orchestration_id is None:
                campaign.consecutive_errors += 1
                entry = _cycle_row(
                    row.number,
                    None,
                    budget_remaining=live.available,
                    error=(row.error or "cycle failed to start")[:500],
                    wave=wave_n,
                    parallel_with=peers,
                )
                cycles.append(entry)
                recorded.append(entry)
                continue

            result = wave_results.get(row.orchestration_id)
            if result is None or isinstance(result, BaseException):
                error_text = str(result) if isinstance(result, BaseException) else (
                    row.error or "cycle failed"
                )
                campaign.consecutive_errors += 1
                entry = _cycle_row(
                    row.number,
                    None,
                    budget_remaining=live.available,
                    error=error_text[:500],
                    wave=wave_n,
                    parallel_with=peers,
                )
                cycles.append(entry)
                recorded.append(entry)
                continue

            campaign.cycles_completed += 1
            failed = (
                result.status is OrchestrationRunStatus.FAILED
                or result.stop_reason == STOP_ERROR
            )
            if failed:
                campaign.consecutive_errors += 1
            else:
                campaign.consecutive_errors = 0
            entry = _cycle_row(
                row.number,
                result,
                budget_remaining=live.available,
                wave=wave_n,
                parallel_with=peers,
            )
            cycles.append(entry)
            recorded.append(entry)
            logger.info(
                "campaign_cycle campaign_id=%s cycle=%s orchestration_id=%s "
                "orch_stop=%s wave=%s budget_remaining=%s",
                campaign.id,
                row.number,
                result.id,
                result.stop_reason,
                wave_n,
                live.available,
            )

        campaign.cycles = cycles
        await db.commit()

        if not recorded:
            continue

        if campaign.cancel_requested or any(
            entry.get("stop_reason") == ORCH_STOP_CANCELLED for entry in recorded
        ):
            return await _finalize(
                db,
                campaign,
                status=ResearchCampaignStatus.COMPLETED,
                stop_reason=STOP_CANCELLED,
                budget_end=live.available,
            )
        if any(entry.get("stop_reason") == STOP_BUDGET_EXHAUSTED for entry in recorded) or (
            live.available <= 0
        ):
            return await _finalize(
                db,
                campaign,
                status=ResearchCampaignStatus.COMPLETED,
                stop_reason=STOP_BUDGET_EXHAUSTED,
                budget_end=live.available,
            )

        wave_hit_cap = any(entry.get("stop_reason") == ORCH_STOP_MAX_PASSES for entry in recorded)
        wave_full_scan = any(
            entry.get("stop_reason") == STOP_NO_OPEN_WORK
            and (entry.get("passes_commissioned") or 0) > 0
            for entry in recorded
        )
        wave_empty_scan = all(
            entry.get("stop_reason") == STOP_NO_OPEN_WORK
            and (entry.get("passes_commissioned") or 0) == 0
            for entry in recorded
            if entry.get("error") is None
        ) and all(entry.get("error") is None for entry in recorded)
        if not wave_hit_cap and (wave_full_scan or wave_empty_scan):
            return await _finalize(
                db,
                campaign,
                status=ResearchCampaignStatus.COMPLETED,
                stop_reason=STOP_NO_OPEN_WORK,
                budget_end=live.available,
            )

        last_error = next(
            (entry.get("error") for entry in reversed(recorded) if entry.get("error")),
            None,
        )
        if campaign.consecutive_errors >= campaign.error_budget:
            return await _finalize(
                db,
                campaign,
                status=ResearchCampaignStatus.COMPLETED,
                stop_reason=STOP_ERROR_BUDGET,
                error=str(last_error) if last_error else None,
                budget_end=live.available,
            )
        # max_passes (or a recoverable cycle error under budget) → next wave.


@dataclass
class CampaignExecutor:
    """The seam :func:`run_campaign_background` resolves at call time.

    Same shape as ``orchestration.OrchestrationExecutor``: production keeps the
    app engine and the real planner; a DB-backed route test rebinds this one
    object so the background loop runs against the test engine with a stub planner.
    """

    session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal
    planner: PlannerFn = agent_run_service.default_plan
    llm: Any | None = None


background_executor = CampaignExecutor()


async def run_campaign_background(campaign_id: UUID) -> None:
    """FastAPI ``BackgroundTask`` entrypoint: run the loop in a fresh session."""
    executor = background_executor
    try:
        async with executor.session_factory() as db:
            await run_campaign(
                db,
                campaign_id,
                planner=executor.planner,
                llm=executor.llm,
            )
        return
    except Exception:
        logger.exception("campaign_background_crashed campaign_id=%s", campaign_id)

    try:
        async with executor.session_factory() as db:
            campaign = await db.get(ResearchCampaign, campaign_id)
            if campaign is not None and campaign.status is ResearchCampaignStatus.RUNNING:
                campaign.status = ResearchCampaignStatus.FAILED
                campaign.stop_reason = STOP_CAMPAIGN_ERROR
                campaign.error = "background campaign crashed unexpectedly"
                await db.commit()
    except Exception:
        logger.exception("campaign_background_finalize_failed campaign_id=%s", campaign_id)


_STALE_RUN_MARGIN_S = 30.0


def _stale_running_cutoff(max_cycles: int | None = None) -> datetime:
    """Worst-case wall-clock for a legitimate campaign + a margin."""
    per_pass = (
        settings.agent_llm_timeout_s * (1 + settings.agent_pass_max_replans)
        + settings.agent_pass_max_runs * settings.toolbench_wall_timeout_s
    )
    per_cycle = settings.orchestration_max_passes * per_pass + _STALE_RUN_MARGIN_S
    cycles = max_cycles if max_cycles is not None else settings.campaign_max_cycles
    ttl = cycles * per_cycle + _STALE_RUN_MARGIN_S
    return datetime.now(UTC) - timedelta(seconds=ttl)


def _sweep_if_stale(campaign: ResearchCampaign) -> bool:
    cutoff = _stale_running_cutoff(campaign.max_cycles)
    if campaign.status is ResearchCampaignStatus.RUNNING and campaign.updated_at < cutoff:
        campaign.status = ResearchCampaignStatus.FAILED
        campaign.stop_reason = STOP_CAMPAIGN_ERROR
        campaign.error = "lost — the background worker did not finish (stale run swept on read)"
        return True
    return False


async def list_project_campaigns(db: AsyncSession, project_id: UUID) -> list[ResearchCampaign]:
    """Newest-first traces for a project, sweeping any stale ``running`` rows first."""
    rows = list(
        (
            await db.execute(
                select(ResearchCampaign)
                .where(ResearchCampaign.project_id == project_id)
                .order_by(ResearchCampaign.created_at.desc())
            )
        ).scalars()
    )
    swept = [_sweep_if_stale(row) for row in rows]
    if any(swept):
        await db.commit()
    return rows


async def get_campaign(db: AsyncSession, campaign_id: UUID) -> ResearchCampaign:
    campaign = await db.get(ResearchCampaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    if _sweep_if_stale(campaign):
        await db.commit()
    return campaign
