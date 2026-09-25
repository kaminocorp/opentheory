"""The project-level orchestration API (0.22.0) — commission a research loop, poll it.

- ``POST /projects/{id}/orchestrations`` — member-gated; mints the ``running``
  trace, schedules the loop in a ``BackgroundTask``, returns ``202``.
- ``GET  /projects/{id}/orchestrations`` — public, newest-first summaries.
- ``GET  /orchestrations/{id}`` — public poll target: the full decision trace.

Same dark-launch flag as agent runs (``AGENT_LOOP_ENABLED``): while off, every
route ``404``s — indistinguishable from a route that does not exist yet.
"""

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, status

from app.api.deps import ActingActor, DbSession, require_agent_loop_enabled
from app.models.orchestration_run import OrchestrationRun
from app.schemas.orchestration import (
    OrchestrationRunRead,
    OrchestrationRunSummary,
    OrchestrationTrigger,
)
from app.services import orchestration as orchestration_service
from app.services.project_members import ensure_is_member

router = APIRouter(dependencies=[Depends(require_agent_loop_enabled)])


@router.post(
    "/projects/{project_id}/orchestrations",
    response_model=OrchestrationRunRead,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["orchestrations"],
)
async def trigger_orchestration(
    project_id: UUID,
    payload: OrchestrationTrigger,
    db: DbSession,
    actor: ActingActor,
    background_tasks: BackgroundTasks,
) -> OrchestrationRun:
    """Commission a bounded multi-thread research loop; returns ``202`` + the running trace."""
    await ensure_is_member(db, project_id, actor)
    run = await orchestration_service.start_orchestration(
        db, project_id, triggered_by=actor, role=payload.role
    )
    background_tasks.add_task(orchestration_service.run_orchestration_background, run.id)
    return run


@router.get(
    "/projects/{project_id}/orchestrations",
    response_model=list[OrchestrationRunSummary],
    tags=["orchestrations"],
)
async def list_orchestrations(project_id: UUID, db: DbSession) -> list[OrchestrationRun]:
    """Public, newest-first orchestration summaries (stale ``running`` rows swept on read)."""
    return await orchestration_service.list_project_orchestrations(db, project_id)


@router.get(
    "/orchestrations/{orchestration_id}",
    response_model=OrchestrationRunRead,
    tags=["orchestrations"],
)
async def get_orchestration(orchestration_id: UUID, db: DbSession) -> OrchestrationRun:
    """Public poll target: the full decision trace of one orchestration (``404`` if unknown)."""
    return await orchestration_service.get_orchestration(db, orchestration_id)
