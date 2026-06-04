from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.actor import Actor
from app.models.claim import Claim
from app.models.thread import Thread
from app.schemas.claim import ClaimCreate
from app.services import contributions


async def create_claim(
    db: AsyncSession, thread_id: UUID, payload: ClaimCreate, actor: Actor
) -> Claim:
    thread = await db.get(Thread, thread_id)
    if thread is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thread not found",
        )

    # A claim inherits the thread's project; project_id is never client-supplied.
    claim = Claim(
        project_id=thread.project_id,
        thread_id=thread.id,
        **payload.model_dump(),
    )
    db.add(claim)
    await db.flush()  # assign claim.id before recording the contribution
    contributions.record_contribution(
        db,
        project_id=thread.project_id,
        actor=actor,
        action=contributions.ACTION_CREATE_CLAIM,
        target_type="claim",
        target_id=claim.id,
    )
    await db.commit()
    await db.refresh(claim)
    return claim


async def list_claims(db: AsyncSession, thread_id: UUID) -> list[Claim]:
    result = await db.execute(
        select(Claim)
        .where(Claim.thread_id == thread_id)
        .order_by(Claim.created_at.desc())
    )
    return list(result.scalars())


async def get_claim(db: AsyncSession, claim_id: UUID) -> Claim:
    claim = await db.get(Claim, claim_id)
    if claim is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Claim not found",
        )
    return claim
