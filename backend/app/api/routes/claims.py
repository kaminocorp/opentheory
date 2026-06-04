from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import ActingActor, DbSession
from app.models.claim import Claim
from app.schemas.claim import ClaimCreate, ClaimRead
from app.services import claims as claim_service

router = APIRouter()


@router.post(
    "/threads/{thread_id}/claims",
    response_model=ClaimRead,
    status_code=status.HTTP_201_CREATED,
    tags=["claims"],
)
async def create_claim(
    thread_id: UUID,
    payload: ClaimCreate,
    db: DbSession,
    actor: ActingActor,
) -> Claim:
    return await claim_service.create_claim(db, thread_id, payload)


@router.get(
    "/threads/{thread_id}/claims",
    response_model=list[ClaimRead],
    tags=["claims"],
)
async def list_claims(thread_id: UUID, db: DbSession) -> list[Claim]:
    return await claim_service.list_claims(db, thread_id)


@router.get("/claims/{claim_id}", response_model=ClaimRead, tags=["claims"])
async def get_claim(claim_id: UUID, db: DbSession) -> Claim:
    return await claim_service.get_claim(db, claim_id)
