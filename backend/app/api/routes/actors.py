from fastapi import APIRouter, HTTPException, status

from app.api.deps import DbSession
from app.core.config import settings
from app.models.actor import Actor
from app.schemas.actor import ActorCreate, ActorRead
from app.services import actors as actor_service

router = APIRouter()


@router.post("", response_model=ActorRead, status_code=status.HTTP_201_CREATED)
async def create_actor(payload: ActorCreate, db: DbSession) -> Actor:
    # Retired in production: real actors are JIT-provisioned from a verified token (0.6.1).
    # The open bootstrap survives only behind the dev flag, for local work and the test suite.
    if not settings.auth_dev_header_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Actor creation is automatic on sign-in; this bootstrap route is disabled",
        )
    return await actor_service.create_actor(db, payload)


@router.get("", response_model=list[ActorRead])
async def list_actors(db: DbSession) -> list[Actor]:
    # Retired in production alongside POST (0.6.1): ActorRead's actor_metadata still holds the
    # verified email (set at JIT provisioning), so an open list would leak every actor's email to
    # any anonymous caller. (external_id + roles moved to the Account; the principal's PII is gated
    # on GET /accounts.) The list survives only behind the dev flag, where it drives the local
    # actor switcher.
    if not settings.auth_dev_header_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Actor listing is disabled; identity is resolved per-request from the token",
        )
    return await actor_service.list_actors(db)
