"""Continuous research campaign (0.25.0) — re-commission the 0.22.0 orchestrator.

``run_campaign`` is contributor infrastructure: it repeatedly commissions
``start_orchestration`` → ``run_orchestration`` against the shared
``ComputeDebit`` / project-budget ceiling, and stops when the pot is empty, no
raisable work remains, the cycle cap is hit, the human cancels, or consecutive
cycle failures exhaust the error budget.

It invents **no** ledger mechanics and never writes a ``Validation`` or a
``FundingAllocation``. Merge / tag stay human/API operations — this loop does
not call ``services/merges.py``.

v1 is **sequential**. One in-flight campaign per project; a running campaign
also blocks a standalone orchestration (they share the pot). Each cycle is one
0.22.0 orchestration, so per-orchestration ``orchestration_max_passes`` still
bounds a single scan; the campaign is what continues after that cap.
"""

from __future__ import annotations

import logging
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
from app.services.agent_runs import PlannerFn
from app.services.orchestration import (
    STOP_BUDGET_EXHAUSTED,
    STOP_ERROR,
    STOP_NO_OPEN_WORK,
    classify_project_threads,
)

logger = logging.getLogger(__name__)

STOP_MAX_CYCLES = "max_cycles"
STOP_CANCELLED = "cancelled"
STOP_ERROR_BUDGET = "error_budget"
STOP_CAMPAIGN_ERROR = "error"


def resolve_max_cycles(requested: int | None) -> int:
    """Clamp a client-supplied cap to the server safety bound (never above settings)."""
    cap = settings.campaign_max_cycles
    if requested is None:
        return cap
    return min(max(1, requested), cap)


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
    )
    db.add(campaign)
    await db.commit()
    return campaign


async def request_cancel(db: AsyncSession, campaign_id: UUID) -> ResearchCampaign:
    """Ask a running campaign to stop after the current cycle. Idempotent while running."""
    campaign = await db.get(ResearchCampaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    if campaign.status is not ResearchCampaignStatus.RUNNING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Campaign is not running",
        )
    campaign.cancel_requested = True
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
        # is visible between cycles — ``get`` would otherwise return the
        # identity-map copy.
        await db.refresh(reloaded)
        return reloaded

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
        if not any(row.eligible for row in classified):
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

        campaign.current_cycle += 1
        cycle_n = campaign.current_cycle
        await db.commit()

        orch: OrchestrationRun | None = None
        try:
            orch = await orchestration_service.start_orchestration(
                db,
                campaign.project_id,
                triggered_by=actor,
                role=campaign.role,
                for_campaign=True,
            )
            finished = await orchestration_service.run_orchestration(
                db, orch.id, planner=planner, llm=llm
            )
        except Exception as exc:
            logger.warning(
                "campaign_cycle_error campaign_id=%s cycle=%s error=%s",
                campaign_id,
                cycle_n,
                exc,
            )
            leftover_id = orch.id if orch is not None else None
            await db.rollback()
            if leftover_id is not None:
                leftover = await db.get(OrchestrationRun, leftover_id)
                if leftover is not None and leftover.status is OrchestrationRunStatus.RUNNING:
                    leftover.status = OrchestrationRunStatus.FAILED
                    leftover.stop_reason = STOP_ERROR
                    leftover.error = str(exc)[:2000]
                    await db.commit()
            campaign = await _reload()
            live = await funding_service.project_budget(db, campaign.project_id)
            campaign.budget_available_end = live.available
            campaign.consecutive_errors += 1
            cycles = list(campaign.cycles)
            cycles.append(
                _cycle_row(cycle_n, None, budget_remaining=live.available, error=str(exc)[:500])
            )
            campaign.cycles = cycles
            await db.commit()
            if campaign.consecutive_errors >= campaign.error_budget:
                return await _finalize(
                    db,
                    campaign,
                    status=ResearchCampaignStatus.COMPLETED,
                    stop_reason=STOP_ERROR_BUDGET,
                    error=str(exc),
                    budget_end=live.available,
                )
            continue

        live = await funding_service.project_budget(db, campaign.project_id)
        campaign = await _reload()
        campaign.budget_available_end = live.available
        campaign.cycles_completed += 1
        cycles = list(campaign.cycles)
        cycles.append(_cycle_row(cycle_n, finished, budget_remaining=live.available))
        campaign.cycles = cycles

        failed = (
            finished.status is OrchestrationRunStatus.FAILED
            or finished.stop_reason == STOP_ERROR
        )
        if failed:
            campaign.consecutive_errors += 1
        else:
            campaign.consecutive_errors = 0
        await db.commit()

        logger.info(
            "campaign_cycle campaign_id=%s cycle=%s orchestration_id=%s "
            "orch_stop=%s budget_remaining=%s",
            campaign.id,
            cycle_n,
            finished.id,
            finished.stop_reason,
            live.available,
        )

        if finished.stop_reason == STOP_BUDGET_EXHAUSTED or live.available <= 0:
            return await _finalize(
                db,
                campaign,
                status=ResearchCampaignStatus.COMPLETED,
                stop_reason=STOP_BUDGET_EXHAUSTED,
                budget_end=live.available,
            )
        if finished.stop_reason == STOP_NO_OPEN_WORK:
            return await _finalize(
                db,
                campaign,
                status=ResearchCampaignStatus.COMPLETED,
                stop_reason=STOP_NO_OPEN_WORK,
                budget_end=live.available,
            )
        if failed and campaign.consecutive_errors >= campaign.error_budget:
            return await _finalize(
                db,
                campaign,
                status=ResearchCampaignStatus.COMPLETED,
                stop_reason=STOP_ERROR_BUDGET,
                error=finished.error,
                budget_end=live.available,
            )
        # max_passes (or a recoverable cycle error under budget) → next cycle.


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
