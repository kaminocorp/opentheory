"""OWNER-only agent session token mint / rotate / revoke (0.55.0).

Dark behind existing auth (``ActingActor`` + ``ensure_can_manage(require_owner=True)``).
No Fly flag. Fail closed when ``AGENT_SESSION_JWT_SECRET`` is missing (503).
Crew UI reveal is slice E — this is the product API only.
"""

from uuid import UUID

from fastapi import APIRouter, Response, status

from app.api.deps import ActingActor, DbSession
from app.schemas.agent_token import AgentTokenMintRead, AgentTokenMintRequest
from app.services import agent_tokens as token_service

router = APIRouter()


@router.post(
    "/projects/{project_id}/agents/{actor_id}/tokens",
    response_model=AgentTokenMintRead,
    status_code=status.HTTP_201_CREATED,
    tags=["agents"],
)
async def mint_agent_token(
    project_id: UUID,
    actor_id: UUID,
    db: DbSession,
    actor: ActingActor,
    payload: AgentTokenMintRequest | None = None,
) -> AgentTokenMintRead:
    ttl = payload.ttl_seconds if payload is not None else None
    row, compact = await token_service.mint_agent_session_token(
        db, project_id, actor_id, actor, ttl_seconds=ttl
    )
    await db.commit()
    return AgentTokenMintRead(token=compact, jti=row.id, expires_at=row.expires_at)


@router.post(
    "/projects/{project_id}/agents/{actor_id}/tokens/{jti}/rotate",
    response_model=AgentTokenMintRead,
    status_code=status.HTTP_201_CREATED,
    tags=["agents"],
)
async def rotate_agent_token(
    project_id: UUID,
    actor_id: UUID,
    jti: UUID,
    db: DbSession,
    actor: ActingActor,
    payload: AgentTokenMintRequest | None = None,
) -> AgentTokenMintRead:
    ttl = payload.ttl_seconds if payload is not None else None
    row, compact = await token_service.rotate_agent_session_token(
        db, project_id, actor_id, jti, actor, ttl_seconds=ttl
    )
    await db.commit()
    return AgentTokenMintRead(token=compact, jti=row.id, expires_at=row.expires_at)


@router.post(
    "/projects/{project_id}/agents/{actor_id}/tokens/{jti}/revoke",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["agents"],
)
async def revoke_agent_token(
    project_id: UUID,
    actor_id: UUID,
    jti: UUID,
    db: DbSession,
    actor: ActingActor,
) -> Response:
    await token_service.revoke_agent_session_token(db, project_id, actor_id, jti, actor)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
