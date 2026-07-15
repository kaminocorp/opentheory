"""The agent-run API surface (0.12.3) — commission a pass, then poll its trace.

Three endpoints, mirroring the toolbench surface (``instruments.py``) and the human-first rule: the
agent uses no parallel path — it composes the *same* ``run_instrument`` chokepoint humans do, one
layer down. The commissioning **human** is accountable (member-gated ``POST``); the agent Actor
authors the work inside the pass.

- ``POST /projects/{id}/threads/{thread_id}/agent-runs`` — member-gated; mints the ``running``
  trace, schedules the pass in a ``BackgroundTask``, returns ``202`` + the pollable trace. The
  multi-second LLM call never blocks the request (Decision #1).
- ``GET  /projects/{id}/threads/{thread_id}/agent-runs`` — public, newest-first trace summaries.
- ``GET  /agent-runs/{id}`` — public poll target: the full trace.

The whole surface is behind the **dark-launch** flag: while ``agent_loop_enabled`` is off, every
route ``404``s (see :func:`require_agent_loop_enabled`) — indistinguishable from a route that does
not exist yet.
"""

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from app.api.deps import ActingActor, DbSession
from app.core.config import settings
from app.models.agent_run import AgentRun
from app.schemas.agent_run import AgentRunRead, AgentRunSummary, AgentRunTrigger
from app.services import agent_runs as agent_run_service
from app.services.project_members import ensure_is_member


async def require_agent_loop_enabled() -> None:
    """Dark-launch gate: while ``agent_loop_enabled`` is off, the whole surface ``404``s.

    Declared as a **router-level** dependency so it runs *before* ``ActingActor``: FastAPI inserts
    router/route ``dependencies`` at the front of the dependency tree, so even an *unauthenticated*
    request sees ``404`` (not ``401``). The flag therefore leaks nothing about the feature — the
    route is indistinguishable from one that is not registered yet, which is the point of a dark
    launch. Production flips the flag when the line is trusted (``docs/operations/deploy.md``).
    """
    if not settings.agent_loop_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")


router = APIRouter(dependencies=[Depends(require_agent_loop_enabled)])


@router.post(
    "/projects/{project_id}/threads/{thread_id}/agent-runs",
    response_model=AgentRunRead,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["agent-runs"],
)
async def trigger_agent_pass(
    project_id: UUID,
    thread_id: UUID,
    payload: AgentRunTrigger,
    db: DbSession,
    actor: ActingActor,
    background_tasks: BackgroundTasks,
) -> AgentRun:
    """Commission one bounded agent pass on a thread; returns ``202`` + the ``running`` trace.

    Order: dark-launch gate (``404`` when off) → authenticate (``ActingActor`` → ``401``) →
    authorize project membership (``ensure_is_member`` → ``404`` missing project / ``403``
    non-member) → mint the ``running`` ``AgentRun`` (``404`` if the thread is not in the project) →
    schedule the pass. The response is the trace in its ``running`` state (serialized before the
    background task runs); the client then polls ``GET /agent-runs/{id}`` until it is
    ``completed``/``failed``.
    """
    await ensure_is_member(db, project_id, actor)
    agent_run = await agent_run_service.start_agent_pass(
        db, project_id, thread_id, triggered_by=actor, role=payload.role
    )
    background_tasks.add_task(agent_run_service.run_agent_pass_background, agent_run.id)
    return agent_run


@router.get(
    "/projects/{project_id}/threads/{thread_id}/agent-runs",
    response_model=list[AgentRunSummary],
    tags=["agent-runs"],
)
async def list_agent_runs(
    project_id: UUID, thread_id: UUID, db: DbSession
) -> list[AgentRun]:
    """Public, newest-first trace summaries for a thread (stale ``running`` rows swept on read)."""
    return await agent_run_service.list_thread_agent_runs(db, project_id, thread_id)


@router.get("/agent-runs/{agent_run_id}", response_model=AgentRunRead, tags=["agent-runs"])
async def get_agent_run(agent_run_id: UUID, db: DbSession) -> AgentRun:
    """Public poll target: the full trace of one pass (``404`` if unknown)."""
    return await agent_run_service.get_agent_run(db, agent_run_id)
