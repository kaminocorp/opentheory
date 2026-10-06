"""Project agent roster — members-only list + OWNER/ADMIN lifecycle (0.57.0).

HTTP is human-only: ``ActingActor`` refuses an agent session token.
Token mint / rotate / revoke stay on ``agent_tokens``. Caps are stored,
not enforced. No Fly flag.
"""

from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import ActingActor, DbSession
from app.schemas.agent_roster import AgentDeployRequest, AgentRosterPatch, AgentRosterRead
from app.services import agent_roster as roster_service

router = APIRouter()


@router.get(
    "/projects/{project_id}/agents",
    response_model=list[AgentRosterRead],
    tags=["agents"],
)
async def list_project_agents(
    project_id: UUID,
    db: DbSession,
    actor: ActingActor,
) -> list[AgentRosterRead]:
    return await roster_service.list_project_agents(db, project_id, actor)


@router.post(
    "/projects/{project_id}/agents",
    response_model=AgentRosterRead,
    status_code=status.HTTP_201_CREATED,
    tags=["agents"],
)
async def deploy_project_agent(
    project_id: UUID,
    payload: AgentDeployRequest,
    db: DbSession,
    actor: ActingActor,
) -> AgentRosterRead:
    row = await roster_service.deploy_project_agent(db, project_id, actor, payload)
    await db.commit()
    return row


@router.patch(
    "/projects/{project_id}/agents/{actor_id}",
    response_model=AgentRosterRead,
    tags=["agents"],
)
async def patch_project_agent(
    project_id: UUID,
    actor_id: UUID,
    payload: AgentRosterPatch,
    db: DbSession,
    actor: ActingActor,
) -> AgentRosterRead:
    row = await roster_service.patch_project_agent(db, project_id, actor_id, actor, payload)
    await db.commit()
    return row
