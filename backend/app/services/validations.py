"""Validation service — recording an assessment *through* the checkpoint chokepoint.

A ``Validation`` is a first-class, immutable assessment (passed / failed / inconclusive /
needs_reproduction / contradicts / retract) of a claim, checkpoint, branch, or artifact.
Per the 0.4.0 plan (Resolved Decision #1) a validation is a ledger event: ``create_validation``
writes the ``Validation`` row **and**, in the same transaction, mints a checkpoint via
``CheckpointService.create_checkpoint`` referencing the validated target (role ``validated``)
and the validation itself (role ``recorded``), recording a ``validate`` contribution.

The checkpoint service remains the sole producer of checkpoints; this service composes with
it (it does not write checkpoints directly). Validations are append-only (enforced in
``app/models/append_only.py``) — a re-assessment is a new row, never an edit.
"""

from collections import defaultdict
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.actor import Actor
from app.models.artifact import Artifact
from app.models.branch import Branch
from app.models.checkpoint import Checkpoint
from app.models.claim import Claim
from app.models.links import CheckpointRef
from app.models.project import Project
from app.models.validation import Validation
from app.schemas.checkpoint import ActorSummary, CheckpointCreate, CheckpointRefInput
from app.schemas.validation import ValidationCreate, ValidationRead
from app.services import checkpoints as checkpoint_service
from app.services import contributions

# Allowed validation target types -> (model whose existence/project we verify, the typed
# FK column on Validation the target id is stored in). Claim/checkpoint/branch are
# exercisable in 0.4.1; artifact is wired here but only covered once artifact writes land
# (plan Decision #4). Evidence is intentionally absent (plan Decision #4).
_TARGET_MODELS: dict[str, type] = {
    "claim": Claim,
    "checkpoint": Checkpoint,
    "branch": Branch,
    "artifact": Artifact,
}
_TARGET_FK: dict[str, str] = {
    "claim": "claim_id",
    "checkpoint": "checkpoint_id",
    "branch": "branch_id",
    "artifact": "artifact_id",
}
VALIDATION_TARGET_TYPES: frozenset[str] = frozenset(_TARGET_MODELS)


def _derive_target(validation: Validation) -> tuple[str | None, UUID | None]:
    """Recover (target_type, target_id) from whichever typed FK is set."""
    if validation.claim_id is not None:
        return "claim", validation.claim_id
    if validation.checkpoint_id is not None:
        return "checkpoint", validation.checkpoint_id
    if validation.branch_id is not None:
        return "branch", validation.branch_id
    if validation.artifact_id is not None:
        return "artifact", validation.artifact_id
    return None, None


def _to_read(
    validation: Validation,
    *,
    actor: ActorSummary | None,
    recording_checkpoint_id: UUID | None,
) -> ValidationRead:
    target_type, target_id = _derive_target(validation)
    return ValidationRead(
        id=validation.id,
        project_id=validation.project_id,
        actor_id=validation.actor_id,
        actor=actor,
        target_type=target_type,
        target_id=target_id,
        outcome=validation.outcome,
        notes=validation.notes,
        recording_checkpoint_id=recording_checkpoint_id,
        created_at=validation.created_at,
        updated_at=validation.updated_at,
    )


async def _enrich(db: AsyncSession, validations: list[Validation]) -> list[ValidationRead]:
    """Resolve actors and recording checkpoints for a set of validations (no N+1)."""
    if not validations:
        return []

    actor_ids = {v.actor_id for v in validations if v.actor_id is not None}
    actors: dict[UUID, ActorSummary] = {}
    if actor_ids:
        rows = await db.execute(select(Actor).where(Actor.id.in_(actor_ids)))
        actors = {actor.id: ActorSummary.model_validate(actor) for actor in rows.scalars()}

    # The recording checkpoint is the one whose ref points at this validation with the
    # ``recorded`` role (written by create_validation via the chokepoint).
    validation_ids = [v.id for v in validations]
    recording: dict[UUID, UUID] = {}
    rows = await db.execute(
        select(CheckpointRef.target_id, CheckpointRef.checkpoint_id).where(
            CheckpointRef.target_type == "validation",
            CheckpointRef.target_id.in_(validation_ids),
            CheckpointRef.role == "recorded",
        )
    )
    for target_id, checkpoint_id in rows:
        recording.setdefault(target_id, checkpoint_id)

    return [
        _to_read(
            v,
            actor=actors.get(v.actor_id) if v.actor_id else None,
            recording_checkpoint_id=recording.get(v.id),
        )
        for v in validations
    ]


async def create_validation(
    db: AsyncSession,
    project_id: UUID,
    payload: ValidationCreate,
    actor: Actor,
) -> ValidationRead:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    model = _TARGET_MODELS.get(payload.target_type)
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"target_type must be one of {sorted(VALIDATION_TARGET_TYPES)}; "
                f"got {payload.target_type!r}"
            ),
        )

    target = await db.get(model, payload.target_id)
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Validation target {payload.target_type} {payload.target_id} not found",
        )
    if target.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Validation target {payload.target_type} {payload.target_id} "
                "belongs to a different project"
            ),
        )

    validation = Validation(
        project_id=project_id,
        actor_id=actor.id,
        outcome=payload.outcome,
        notes=payload.notes,
        **{_TARGET_FK[payload.target_type]: payload.target_id},
    )
    db.add(validation)
    await db.flush()  # assign validation.id before referencing it from the checkpoint

    # Record the assessment through the checkpoint chokepoint: one ref to the validated
    # target, one ref back to the validation. The chokepoint owns the single commit, so
    # the validation row, the checkpoint, its refs, and the contribution persist atomically.
    extra_refs = [
        CheckpointRefInput(
            target_type=payload.target_type,
            target_id=payload.target_id,
            role="validated",
        ),
        CheckpointRefInput(
            target_type="validation",
            target_id=validation.id,
            role="recorded",
        ),
    ]
    # Scope the checkpoint to the claim's thread when validating a claim (optional
    # metadata) so it lands on the right line in the timeline; otherwise project-level.
    thread_id = target.thread_id if payload.target_type == "claim" else None
    checkpoint_payload = CheckpointCreate(
        thread_id=thread_id,
        summary=f"Validation ({payload.outcome.value}) on {payload.target_type}",
        content={
            "validation_id": str(validation.id),
            "outcome": payload.outcome.value,
            "target_type": payload.target_type,
            "target_id": str(payload.target_id),
        },
    )
    await checkpoint_service.create_checkpoint(
        db,
        project_id,
        checkpoint_payload,
        actor,
        extra_refs=extra_refs,
        contribution_action=contributions.ACTION_VALIDATE,
    )

    # The chokepoint committed; expire_on_commit=False keeps validation's attributes, and
    # the ``recorded`` ref now exists, so _enrich resolves the recording checkpoint.
    return (await _enrich(db, [validation]))[0]


async def list_validations(db: AsyncSession, project_id: UUID) -> list[ValidationRead]:
    result = await db.execute(
        select(Validation)
        .where(Validation.project_id == project_id)
        .order_by(Validation.created_at.desc())
    )
    return await _enrich(db, list(result.scalars()))


async def list_validations_for_claim(db: AsyncSession, claim_id: UUID) -> list[ValidationRead]:
    result = await db.execute(
        select(Validation)
        .where(Validation.claim_id == claim_id)
        .order_by(Validation.created_at.desc())
    )
    return await _enrich(db, list(result.scalars()))


async def validations_by_claim(
    db: AsyncSession, claim_ids: list[UUID]
) -> dict[UUID, list[ValidationRead]]:
    """Batched: every claim's validations (oldest first), keyed by claim id.

    Used by the claim read model (0.4.4) to embed validation history without an N+1. The
    keys are the claim ids (each claim-target ValidationRead carries the claim as its
    ``target_id``); claims with no validations are simply absent from the map.
    """
    if not claim_ids:
        return {}
    result = await db.execute(
        select(Validation)
        .where(Validation.claim_id.in_(claim_ids))
        .order_by(Validation.created_at.asc())
    )
    reads = await _enrich(db, list(result.scalars()))
    grouped: dict[UUID, list[ValidationRead]] = defaultdict(list)
    for read in reads:
        if read.target_id is not None:
            grouped[read.target_id].append(read)
    return dict(grouped)


async def get_validation(db: AsyncSession, validation_id: UUID) -> ValidationRead:
    validation = await db.get(Validation, validation_id)
    if validation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Validation not found",
        )
    return (await _enrich(db, [validation]))[0]
