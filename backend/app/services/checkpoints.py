"""Checkpoint service — the single sanctioned producer of ledger checkpoints.

``create_checkpoint`` is the only entry point that writes a ``Checkpoint``. It validates
project/thread/parent/ref context, writes one ``checkpoint_refs`` row per referenced
primitive, links parent checkpoints, and auto-records a ``Contribution`` — all in one
transaction. Checkpoints and their refs are append-only (enforced in
``app/models/append_only.py``); there is deliberately no update or delete path.

Thread/claim/evidence creates do **not** auto-promote to a checkpoint — promotion is a
separate, explicit user action (plan Resolved Decision #3).
"""

from collections import defaultdict
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.actor import Actor
from app.models.artifact import Artifact
from app.models.branch import Branch
from app.models.checkpoint import Checkpoint
from app.models.claim import Claim
from app.models.contribution import Contribution
from app.models.enums import BranchStatus
from app.models.evidence import Evidence
from app.models.links import CheckpointRef
from app.models.project import Project
from app.models.thread import Thread
from app.models.validation import Validation
from app.schemas.checkpoint import (
    ActorSummary,
    CheckpointCreate,
    CheckpointRead,
    CheckpointRefInput,
    CheckpointRefRead,
)
from app.services import contributions

# Allowed checkpoint-ref target types -> the model whose existence/project we verify,
# plus the attribute used as the human-readable label (0.3.4 enriched read). 0.4.1 adds
# ``validation`` and ``branch`` so the validation flow (and later branch flows) can record
# refs that resolve labels like any other primitive.
_REF_TARGET_MODELS: dict[str, type] = {
    "claim": Claim,
    "evidence": Evidence,
    "artifact": Artifact,
    "thread": Thread,
    "branch": Branch,
    "validation": Validation,
}
_REF_LABEL_ATTR: dict[str, str] = {
    "claim": "statement",
    "evidence": "title",
    "artifact": "name",
    "thread": "title",
    "branch": "name",
    "validation": "outcome",
}
CHECKPOINT_TARGET_TYPES: frozenset[str] = frozenset(_REF_TARGET_MODELS)


def _to_read(
    checkpoint: Checkpoint,
    *,
    author: ActorSummary | None,
    contribution_kind: str | None,
    labels: dict[tuple[str, UUID], str],
) -> CheckpointRead:
    return CheckpointRead(
        id=checkpoint.id,
        project_id=checkpoint.project_id,
        thread_id=checkpoint.thread_id,
        branch_id=checkpoint.branch_id,
        author_id=checkpoint.author_id,
        author=author,
        contribution_kind=contribution_kind,
        stage=checkpoint.stage,
        summary=checkpoint.summary,
        content=checkpoint.content,
        notes=checkpoint.notes,
        parent_ids=[parent.id for parent in checkpoint.parents],
        refs=[
            CheckpointRefRead(
                id=ref.id,
                target_type=ref.target_type,
                target_id=ref.target_id,
                role=ref.role,
                label=labels.get((ref.target_type, ref.target_id)),
            )
            for ref in checkpoint.refs
        ],
        created_at=checkpoint.created_at,
        updated_at=checkpoint.updated_at,
    )


async def _enrich(db: AsyncSession, checkpoints: list[Checkpoint]) -> list[CheckpointRead]:
    """Resolve authors, contribution kinds, and ref labels for a set of checkpoints.

    Batched (no N+1): one query for authors, one for contributions, one per referenced
    target type.
    """
    if not checkpoints:
        return []

    # Authors.
    author_ids = {c.author_id for c in checkpoints if c.author_id is not None}
    authors: dict[UUID, ActorSummary] = {}
    if author_ids:
        rows = await db.execute(select(Actor).where(Actor.id.in_(author_ids)))
        authors = {actor.id: ActorSummary.model_validate(actor) for actor in rows.scalars()}

    # Contribution kind recorded for each checkpoint (only create_checkpoint sets
    # checkpoint_id in 0.3.x, so this is unambiguous).
    checkpoint_ids = [c.id for c in checkpoints]
    contribution_kind: dict[UUID, str] = {}
    rows = await db.execute(
        select(Contribution.checkpoint_id, Contribution.action).where(
            Contribution.checkpoint_id.in_(checkpoint_ids)
        )
    )
    for checkpoint_id, action in rows:
        contribution_kind.setdefault(checkpoint_id, action)

    # Ref labels, grouped by target type so each type is one query.
    ids_by_type: dict[str, set[UUID]] = defaultdict(set)
    for checkpoint in checkpoints:
        for ref in checkpoint.refs:
            ids_by_type[ref.target_type].add(ref.target_id)
    labels: dict[tuple[str, UUID], str] = {}
    for target_type, ids in ids_by_type.items():
        model = _REF_TARGET_MODELS.get(target_type)
        attr = _REF_LABEL_ATTR.get(target_type)
        if model is None or attr is None:
            continue
        rows = await db.execute(select(model).where(model.id.in_(ids)))
        for obj in rows.scalars():
            labels[(target_type, obj.id)] = getattr(obj, attr)

    return [
        _to_read(
            checkpoint,
            author=authors.get(checkpoint.author_id) if checkpoint.author_id else None,
            contribution_kind=contribution_kind.get(checkpoint.id),
            labels=labels,
        )
        for checkpoint in checkpoints
    ]


async def _load_for_read(db: AsyncSession, checkpoint_id: UUID) -> Checkpoint | None:
    result = await db.execute(
        select(Checkpoint)
        .where(Checkpoint.id == checkpoint_id)
        .options(selectinload(Checkpoint.parents), selectinload(Checkpoint.refs))
    )
    return result.scalar_one_or_none()


async def _validate_parents(
    db: AsyncSession, project_id: UUID, parent_ids: list[UUID]
) -> list[Checkpoint]:
    parents: list[Checkpoint] = []
    seen: set[UUID] = set()
    for parent_id in parent_ids:
        if parent_id in seen:
            continue
        seen.add(parent_id)
        parent = await db.get(Checkpoint, parent_id)
        if parent is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Parent checkpoint {parent_id} not found",
            )
        if parent.project_id != project_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Parent checkpoint {parent_id} belongs to a different project",
            )
        parents.append(parent)
    return parents


async def _validate_refs(
    db: AsyncSession, project_id: UUID, refs: list[CheckpointRefInput]
) -> None:
    for ref in refs:
        model = _REF_TARGET_MODELS.get(ref.target_type)
        if model is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"target_type must be one of {sorted(CHECKPOINT_TARGET_TYPES)}; "
                    f"got {ref.target_type!r}"
                ),
            )
        target = await db.get(model, ref.target_id)
        if target is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Referenced {ref.target_type} {ref.target_id} not found",
            )
        if target.project_id != project_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Referenced {ref.target_type} {ref.target_id} "
                    "belongs to a different project"
                ),
            )


async def create_checkpoint(
    db: AsyncSession,
    project_id: UUID,
    payload: CheckpointCreate,
    actor: Actor,
    *,
    extra_refs: list[CheckpointRefInput] | None = None,
    contribution_action: str | None = None,
) -> CheckpointRead:
    """Create the project's sole kind of ledger write: an immutable checkpoint.

    ``extra_refs`` are service-supplied refs (e.g. the validation flow adds a
    ``validated`` ref to the target and a ``recorded`` ref to the validation). They are
    trusted — unlike client ``payload.refs`` they are not re-validated here, because the
    calling service has already validated the underlying rows in the same transaction.
    ``contribution_action`` overrides the recorded contribution's action (default
    ``create_checkpoint``) so flows like ``validate`` attribute correctly while still
    going through this one chokepoint.
    """
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    if payload.thread_id is not None:
        thread = await db.get(Thread, payload.thread_id)
        if thread is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Thread not found",
            )
        if thread.project_id != project_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Thread belongs to a different project",
            )

    if payload.branch_id is not None:
        branch = await db.get(Branch, payload.branch_id)
        if branch is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Branch not found",
            )
        if branch.project_id != project_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Branch belongs to a different project",
            )
        # Only an open branch can receive new checkpoints; a closed/dead-end/merged line
        # is sealed (its dead ends are preserved, not extended).
        if branch.status != BranchStatus.OPEN:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Branch is not open (status: {branch.status.value})",
            )

    parents = await _validate_parents(db, project_id, payload.parent_ids)
    await _validate_refs(db, project_id, payload.refs)

    checkpoint = Checkpoint(
        project_id=project_id,
        thread_id=payload.thread_id,
        branch_id=payload.branch_id,
        author_id=actor.id,
        stage=payload.stage,
        summary=payload.summary,
        content=payload.content,
        notes=payload.notes,
    )
    checkpoint.parents = parents
    db.add(checkpoint)
    await db.flush()  # assign checkpoint.id before refs/contribution

    for ref in [*payload.refs, *(extra_refs or [])]:
        db.add(
            CheckpointRef(
                checkpoint_id=checkpoint.id,
                target_type=ref.target_type,
                target_id=ref.target_id,
                role=ref.role,
            )
        )

    contributions.record_contribution(
        db,
        project_id=project_id,
        actor=actor,
        action=contribution_action or contributions.ACTION_CREATE_CHECKPOINT,
        target_type="checkpoint",
        target_id=checkpoint.id,
        checkpoint_id=checkpoint.id,
    )

    await db.commit()

    loaded = await _load_for_read(db, checkpoint.id)
    assert loaded is not None  # just committed
    return (await _enrich(db, [loaded]))[0]


async def list_checkpoints(db: AsyncSession, project_id: UUID) -> list[CheckpointRead]:
    result = await db.execute(
        select(Checkpoint)
        .where(Checkpoint.project_id == project_id)
        .options(selectinload(Checkpoint.parents), selectinload(Checkpoint.refs))
        .order_by(Checkpoint.created_at.desc())
    )
    return await _enrich(db, list(result.scalars()))


async def list_checkpoints_for_branch(
    db: AsyncSession, branch_id: UUID
) -> list[CheckpointRead]:
    """Checkpoints recorded on a branch (newest first); used by the branch detail read."""
    result = await db.execute(
        select(Checkpoint)
        .where(Checkpoint.branch_id == branch_id)
        .options(selectinload(Checkpoint.parents), selectinload(Checkpoint.refs))
        .order_by(Checkpoint.created_at.desc())
    )
    return await _enrich(db, list(result.scalars()))


async def get_checkpoint(db: AsyncSession, checkpoint_id: UUID) -> CheckpointRead:
    checkpoint = await _load_for_read(db, checkpoint_id)
    if checkpoint is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Checkpoint not found",
        )
    return (await _enrich(db, [checkpoint]))[0]
