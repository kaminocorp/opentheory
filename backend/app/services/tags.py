"""Tag service — named immutable pointers at checkpoints (0.21.0).

A ``Tag`` is a lightweight annotation: it names a checkpoint without rewriting it.
Create composes through the checkpoint chokepoint (one recording checkpoint, a
``tag`` contribution, a ``created`` ref back to the tag). Tags are append-only —
a rename or retarget is a new row; a colliding name is ``409``, never an overwrite.

The recording checkpoint lands on the tagged checkpoint's line when that line is
still open, otherwise on the main line — so a sealed / merged branch can still be
tagged without violating the "no writes on a sealed line" rule.
"""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.actor import Actor
from app.models.branch import Branch
from app.models.checkpoint import Checkpoint
from app.models.enums import BranchStatus
from app.models.links import CheckpointRef
from app.models.project import Project
from app.models.tag import Tag
from app.schemas.checkpoint import ActorSummary, CheckpointCreate, CheckpointRefInput
from app.schemas.tag import TagCreate, TagRead
from app.services import checkpoints as checkpoint_service
from app.services import contributions


def _to_read(
    tag: Tag,
    *,
    author: ActorSummary | None,
    recording_checkpoint_id: UUID | None,
) -> TagRead:
    return TagRead(
        id=tag.id,
        project_id=tag.project_id,
        checkpoint_id=tag.checkpoint_id,
        author_id=tag.author_id,
        author=author,
        name=tag.name,
        kind=tag.kind,
        notes=tag.notes,
        recording_checkpoint_id=recording_checkpoint_id,
        created_at=tag.created_at,
        updated_at=tag.updated_at,
    )


async def _enrich(db: AsyncSession, tags: list[Tag]) -> list[TagRead]:
    if not tags:
        return []

    author_ids = {tag.author_id for tag in tags if tag.author_id is not None}
    authors: dict[UUID, ActorSummary] = {}
    if author_ids:
        rows = await db.execute(select(Actor).where(Actor.id.in_(author_ids)))
        authors = {actor.id: ActorSummary.model_validate(actor) for actor in rows.scalars()}

    tag_ids = [tag.id for tag in tags]
    recording: dict[UUID, UUID] = {}
    rows = await db.execute(
        select(CheckpointRef.target_id, CheckpointRef.checkpoint_id).where(
            CheckpointRef.target_type == "tag",
            CheckpointRef.target_id.in_(tag_ids),
            CheckpointRef.role == "created",
        )
    )
    for target_id, checkpoint_id in rows:
        recording.setdefault(target_id, checkpoint_id)

    return [
        _to_read(
            tag,
            author=authors.get(tag.author_id) if tag.author_id else None,
            recording_checkpoint_id=recording.get(tag.id),
        )
        for tag in tags
    ]


async def _recording_branch_id(db: AsyncSession, tagged: Checkpoint) -> UUID | None:
    """Where the tag-event checkpoint may land.

    Sealed / merged lines cannot receive new checkpoints (``create_checkpoint``
    enforces this). A tag of historical work still records — on the main line.
    """
    if tagged.branch_id is None:
        return None
    branch = await db.get(Branch, tagged.branch_id)
    if branch is None or branch.status != BranchStatus.OPEN:
        return None
    return tagged.branch_id


async def create_tag(
    db: AsyncSession,
    project_id: UUID,
    payload: TagCreate,
    actor: Actor,
) -> TagRead:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    existing = await db.execute(
        select(Tag.id).where(Tag.project_id == project_id, Tag.name == payload.name)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A tag named {payload.name!r} already exists on this project",
        )

    tagged = await db.get(Checkpoint, payload.checkpoint_id)
    if tagged is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Checkpoint not found",
        )
    if tagged.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Checkpoint belongs to a different project",
        )

    tag = Tag(
        project_id=project_id,
        checkpoint_id=payload.checkpoint_id,
        author_id=actor.id,
        name=payload.name,
        kind=payload.kind,
        notes=payload.notes,
    )
    db.add(tag)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A tag named {payload.name!r} already exists on this project",
        ) from exc

    recording_branch_id = await _recording_branch_id(db, tagged)
    await checkpoint_service.create_checkpoint(
        db,
        project_id,
        CheckpointCreate(
            thread_id=tagged.thread_id,
            branch_id=recording_branch_id,
            summary=f"Tagged '{payload.name}' ({payload.kind.value})",
            content={
                "tag_id": str(tag.id),
                "name": payload.name,
                "kind": payload.kind.value,
                "tagged_checkpoint_id": str(payload.checkpoint_id),
            },
            notes=payload.notes,
        ),
        actor,
        extra_refs=[
            CheckpointRefInput(target_type="tag", target_id=tag.id, role="created"),
        ],
        contribution_action=contributions.ACTION_TAG,
    )

    return (await _enrich(db, [tag]))[0]


async def list_tags(db: AsyncSession, project_id: UUID) -> list[TagRead]:
    # Existing project → 200 + a (possibly empty) list. Unknown project → 404,
    # not a silent empty that pretends the project exists. The client treats a
    # missing *route* as empty; a missing *project* stays a 404.
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    result = await db.execute(
        select(Tag).where(Tag.project_id == project_id).order_by(Tag.created_at.desc())
    )
    return await _enrich(db, list(result.scalars()))


async def get_tag(db: AsyncSession, tag_id: UUID) -> TagRead:
    tag = await db.get(Tag, tag_id)
    if tag is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tag not found",
        )
    return (await _enrich(db, [tag]))[0]
