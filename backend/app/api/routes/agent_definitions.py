"""Account-owned agent definition catalog (0.59.0).

HTTP is human-only: ``ActingActor`` refuses an agent session token.
Writes require an Account. Family rollup is a read join.
"""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.api.deps import ActingActor, DbSession
from app.models.actor import Actor
from app.schemas.agent_definition import (
    AgentDefinitionCreate,
    AgentDefinitionPatch,
    AgentDefinitionRead,
    AgentDefinitionVersionCreate,
    AgentFamilyRollupRead,
)
from app.services import agent_definitions as catalog_service

router = APIRouter()


def _account_id(actor: Actor) -> UUID:
    if actor.account_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acting actor has no account",
        )
    return actor.account_id


@router.get(
    "/agent-definitions/families/{family_id}",
    response_model=AgentFamilyRollupRead,
    tags=["agent-definitions"],
)
async def get_agent_family(
    family_id: UUID,
    db: DbSession,
    actor: ActingActor,
) -> AgentFamilyRollupRead:
    return await catalog_service.family_rollup(db, family_id, actor)


@router.get(
    "/agent-definitions",
    response_model=list[AgentDefinitionRead],
    tags=["agent-definitions"],
)
async def list_agent_definitions(
    db: DbSession,
    actor: ActingActor,
) -> list[AgentDefinitionRead]:
    return await catalog_service.list_definitions(db, _account_id(actor))


@router.post(
    "/agent-definitions",
    response_model=AgentDefinitionRead,
    status_code=status.HTTP_201_CREATED,
    tags=["agent-definitions"],
)
async def create_agent_definition(
    payload: AgentDefinitionCreate,
    db: DbSession,
    actor: ActingActor,
) -> AgentDefinitionRead:
    row = await catalog_service.create_definition(db, _account_id(actor), payload)
    await db.commit()
    return row


@router.get(
    "/agent-definitions/{definition_id}",
    response_model=AgentDefinitionRead,
    tags=["agent-definitions"],
)
async def get_agent_definition(
    definition_id: UUID,
    db: DbSession,
    actor: ActingActor,
) -> AgentDefinitionRead:
    return await catalog_service.get_readable_definition(db, definition_id, actor)


@router.patch(
    "/agent-definitions/{definition_id}",
    response_model=AgentDefinitionRead,
    tags=["agent-definitions"],
)
async def patch_agent_definition(
    definition_id: UUID,
    payload: AgentDefinitionPatch,
    db: DbSession,
    actor: ActingActor,
) -> AgentDefinitionRead:
    row = await catalog_service.patch_definition(
        db, definition_id, _account_id(actor), payload
    )
    await db.commit()
    return row


@router.post(
    "/agent-definitions/{definition_id}/versions",
    response_model=AgentDefinitionRead,
    status_code=status.HTTP_201_CREATED,
    tags=["agent-definitions"],
)
async def create_agent_definition_version(
    definition_id: UUID,
    payload: AgentDefinitionVersionCreate,
    db: DbSession,
    actor: ActingActor,
) -> AgentDefinitionRead:
    row = await catalog_service.create_version(
        db, definition_id, _account_id(actor), payload
    )
    await db.commit()
    return row
