"""Semantic research-git blame — public ledger read (0.36.0).

``GET /projects/{id}/claims/{claim_id}/blame``. Always-on, mints nothing. Same
posture as semantic diff (0.29.0) and checkpoint list / get: a derived read
over the append-only graph, not a write and not an instrument.
"""

from uuid import UUID

from fastapi import APIRouter

from app.api.deps import DbSession
from app.schemas.blame import ClaimBlameRead
from app.services import blame as blame_service

router = APIRouter()


@router.get(
    "/projects/{project_id}/claims/{claim_id}/blame",
    response_model=ClaimBlameRead,
    tags=["blame"],
)
async def get_claim_blame(
    project_id: UUID,
    claim_id: UUID,
    db: DbSession,
) -> ClaimBlameRead:
    return await blame_service.blame_claim(db, project_id, claim_id)
