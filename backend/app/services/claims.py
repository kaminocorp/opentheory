from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.actor import Actor
from app.models.claim import Claim
from app.models.enums import ValidationOutcome
from app.models.thread import Thread
from app.schemas.claim import ClaimCreate, ClaimRead, ClaimSignal
from app.schemas.validation import ValidationRead
from app.services import contributions
from app.services import validations as validation_service

_CONTRADICTION_OUTCOMES = {ValidationOutcome.CONTRADICTS, ValidationOutcome.FAILED}


def compute_signal(validations: list[ValidationRead]) -> ClaimSignal:
    """Derive a claim's display signal from its validation history (plan Decision #5).

    Walks the history **in chronological order** (oldest first — the order every caller
    passes): a ``contradicts``/``failed`` contests the claim, a later ``retract`` clears
    the contest, and a still-later ``contradicts`` contests it again. So the latest
    decisive event wins, rather than a single ``retract`` anywhere clearing every
    contradiction. Absent a live contradiction, a ``passed`` makes it ``validated``. This
    is a *display* signal — the stored ``Claim.status`` is untouched.
    """
    contested = False
    validated = False
    for validation in validations:  # oldest first
        if validation.outcome in _CONTRADICTION_OUTCOMES:
            contested = True
        elif validation.outcome == ValidationOutcome.RETRACT:
            contested = False
        elif validation.outcome == ValidationOutcome.PASSED:
            validated = True
    if contested:
        return "contested"
    if validated:
        return "validated"
    return "none"


def _to_read(claim: Claim, validations: list[ValidationRead]) -> ClaimRead:
    return ClaimRead(
        id=claim.id,
        project_id=claim.project_id,
        thread_id=claim.thread_id,
        kind=claim.kind,
        status=claim.status,
        statement=claim.statement,
        rationale=claim.rationale,
        confidence=float(claim.confidence) if claim.confidence is not None else None,
        claim_metadata=claim.claim_metadata,
        created_at=claim.created_at,
        updated_at=claim.updated_at,
        validations=validations,
        signal=compute_signal(validations),
    )


async def create_claim(
    db: AsyncSession, thread_id: UUID, payload: ClaimCreate, actor: Actor
) -> ClaimRead:
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
    return _to_read(claim, [])  # a fresh claim has no validations yet


async def list_claims(db: AsyncSession, thread_id: UUID) -> list[ClaimRead]:
    result = await db.execute(
        select(Claim)
        .where(Claim.thread_id == thread_id)
        .order_by(Claim.created_at.desc())
    )
    claims = list(result.scalars())
    by_claim = await validation_service.validations_by_claim(db, [c.id for c in claims])
    return [_to_read(claim, by_claim.get(claim.id, [])) for claim in claims]


async def get_claim(db: AsyncSession, claim_id: UUID) -> ClaimRead:
    claim = await db.get(Claim, claim_id)
    if claim is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Claim not found",
        )
    by_claim = await validation_service.validations_by_claim(db, [claim.id])
    return _to_read(claim, by_claim.get(claim.id, []))
