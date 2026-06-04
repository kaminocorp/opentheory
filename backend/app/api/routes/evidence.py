from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import ActingActor, DbSession
from app.schemas.evidence import EvidenceCreate, EvidenceRead
from app.services import evidence as evidence_service

router = APIRouter()


@router.post(
    "/claims/{claim_id}/evidence",
    response_model=EvidenceRead,
    status_code=status.HTTP_201_CREATED,
    tags=["evidence"],
)
async def attach_evidence(
    claim_id: UUID,
    payload: EvidenceCreate,
    db: DbSession,
    actor: ActingActor,
) -> EvidenceRead:
    return await evidence_service.attach_evidence(db, claim_id, payload)


@router.get(
    "/claims/{claim_id}/evidence",
    response_model=list[EvidenceRead],
    tags=["evidence"],
)
async def list_evidence(claim_id: UUID, db: DbSession) -> list[EvidenceRead]:
    return await evidence_service.list_evidence(db, claim_id)
