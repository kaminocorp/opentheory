"""The continuous research campaign API (0.25.0) — start, stop, poll.

- ``POST /projects/{id}/campaigns`` — member-gated; mints the ``running``
  campaign, schedules the loop in a ``BackgroundTask``, returns ``202``.
- ``POST /campaigns/{id}/cancel`` — member-gated; requests a stop before the
  next cycle (in-flight orchestrations are flagged to stop between waves).
- ``GET  /projects/{id}/campaigns`` — public, newest-first summaries.
- ``GET  /campaigns/{id}`` — public poll target: the full cycle trace.

Same dark-launch flag as agent runs and orchestrations (``AGENT_LOOP_ENABLED``):
while off, every route ``404``s — indistinguishable from a route that does not
exist yet. One flag for the whole agent family — not a second switch.
"""

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, status

from app.api.deps import ActingActor, DbSession, require_agent_loop_enabled
from app.models.research_campaign import ResearchCampaign
from app.schemas.campaign import CampaignTrigger, ResearchCampaignRead, ResearchCampaignSummary
from app.services import campaigns as campaign_service
from app.services.project_members import ensure_is_member

router = APIRouter(dependencies=[Depends(require_agent_loop_enabled)])


@router.post(
    "/projects/{project_id}/campaigns",
    response_model=ResearchCampaignRead,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["campaigns"],
)
async def trigger_campaign(
    project_id: UUID,
    payload: CampaignTrigger,
    db: DbSession,
    actor: ActingActor,
    background_tasks: BackgroundTasks,
) -> ResearchCampaign:
    """Start a continuous research campaign; returns ``202`` + the running trace."""
    await ensure_is_member(db, project_id, actor)
    campaign = await campaign_service.start_campaign(
        db,
        project_id,
        triggered_by=actor,
        role=payload.role,
        max_cycles=payload.max_cycles,
    )
    background_tasks.add_task(campaign_service.run_campaign_background, campaign.id)
    return campaign


@router.post(
    "/campaigns/{campaign_id}/cancel",
    response_model=ResearchCampaignRead,
    tags=["campaigns"],
)
async def cancel_campaign(
    campaign_id: UUID,
    db: DbSession,
    actor: ActingActor,
) -> ResearchCampaign:
    """Request a stop before the next cycle.

    In-flight orchestrations are flagged so they can halt between waves.
    The campaign stays ``running`` until the loop honours the flag.
    """
    campaign = await campaign_service.get_campaign(db, campaign_id)
    await ensure_is_member(db, campaign.project_id, actor)
    return await campaign_service.request_cancel(db, campaign_id)


@router.get(
    "/projects/{project_id}/campaigns",
    response_model=list[ResearchCampaignSummary],
    tags=["campaigns"],
)
async def list_campaigns(project_id: UUID, db: DbSession) -> list[ResearchCampaign]:
    """Public, newest-first campaign summaries (stale ``running`` rows swept on read)."""
    return await campaign_service.list_project_campaigns(db, project_id)


@router.get(
    "/campaigns/{campaign_id}",
    response_model=ResearchCampaignRead,
    tags=["campaigns"],
)
async def get_campaign(campaign_id: UUID, db: DbSession) -> ResearchCampaign:
    """Public poll target: the full cycle trace of one campaign (``404`` if unknown)."""
    return await campaign_service.get_campaign(db, campaign_id)
