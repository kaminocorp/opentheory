"""Semantic research-git diff — derived read over two ledger tips (0.29.0).

A ``git diff`` for research space: claims / validation signal / grounding /
instrument outcomes between two checkpoints (or the tips a branch / tag / ``main``
name resolves to). Deterministic. Mints nothing. Same two tips → same payload.

State at a tip is reconstructed from the ancestor closure of that checkpoint
(the DAG walk through ``checkpoint_parents``, including multi-parent merges):

- **Claim presence.** Referenced by any ancestor checkpoint, or created at or
  before the tip and never referenced on any checkpoint (an uncommitted claim
  is a project fact, visible once it exists).
- **Signal.** ``compute_signal`` over validations whose *recording* checkpoint
  is in the ancestor set — so a validation minted on another line does not leak.
- **Grounding.** Evidence recorded on an ancestor checkpoint, plus hand-attached
  evidence (no recording checkpoint) whose ``created_at`` is at or before the tip.
- **Instruments.** ``tool_invocations`` on checkpoints in ``from..to``
  (ancestors of ``to`` minus ancestors of ``from``).

Unknown refs are ``404``. The function never writes.
"""

from collections import defaultdict
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.branch import Branch
from app.models.checkpoint import Checkpoint, checkpoint_parent
from app.models.claim import Claim
from app.models.evidence import Evidence
from app.models.links import CheckpointRef, ClaimEvidenceLink
from app.models.project import Project
from app.models.tag import Tag
from app.models.validation import Validation
from app.schemas.claim import ClaimGrounding, ClaimSignal
from app.schemas.diff import (
    Ancestry,
    ClaimDelta,
    GroundingMove,
    InstrumentOutcome,
    ResolvedRef,
    SemanticDiffRead,
)
from app.schemas.validation import ValidationRead
from app.services import claims as claim_service
from app.services import grounding as grounding_service

# Tokens that resolve to the project's main line (``branch_id IS NULL``) tip.
_MAIN_ALIASES = frozenset({"main", "mainline", "@main", "head"})

_UNKNOWN_REF = "unknown ref: {value}"


def walk_ancestors(start: UUID, parent_map: dict[UUID, list[UUID]]) -> set[UUID]:
    """Inclusive ancestor closure of ``start`` (self + parents, transitively).

    Multi-parent merge nodes union every parent. A missing node (no parents
    recorded) still contributes itself. Cycles are ignored — the ledger must
    not have them; the seen-set is a belt.
    """
    seen: set[UUID] = set()
    stack = [start]
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        stack.extend(parent_map.get(current, ()))
    return seen


def lowest_common_ancestor(
    from_anc: set[UUID],
    to_anc: set[UUID],
    parent_map: dict[UUID, list[UUID]],
    created_at: dict[UUID, datetime],
) -> UUID | None:
    """Newest lowest common ancestor, or ``None`` when the tips do not meet.

    An LCA is a common ancestor that is not a proper ancestor of another common
    ancestor. Several LCAs can exist on a diamond; we pick the newest
    ``(created_at, id)`` so the payload stays deterministic.
    """
    common = from_anc & to_anc
    if not common:
        return None
    proper_ancestors: set[UUID] = set()
    for node in common:
        for parent in parent_map.get(node, ()):
            proper_ancestors |= walk_ancestors(parent, parent_map)
    lcas = [node for node in common if node not in proper_ancestors]
    if not lcas:
        # Degenerate: every common node is an ancestor of another. Fall back to
        # the newest common ancestor so the field is still honest.
        lcas = list(common)
    lcas.sort(key=lambda node: (created_at.get(node, datetime.min), node), reverse=True)
    return lcas[0]


def sort_checkpoint_ids(
    ids: set[UUID], created_at: dict[UUID, datetime]
) -> list[UUID]:
    """Stable chronological order: ``created_at`` then ``id``."""
    return sorted(ids, key=lambda node: (created_at.get(node, datetime.min), node))


def classify_claim_delta(
    *,
    claim_id: UUID,
    statement: str,
    present_from: bool,
    present_to: bool,
    from_signal: ClaimSignal,
    to_signal: ClaimSignal,
) -> ClaimDelta | None:
    """Presence + signal → at most one claim row. Pure; no I/O."""
    if present_to and not present_from:
        return ClaimDelta(
            claim_id=claim_id,
            statement=statement,
            change="added",
            from_signal=None,
            to_signal=to_signal,
        )
    if present_from and not present_to:
        return ClaimDelta(
            claim_id=claim_id,
            statement=statement,
            change="removed",
            from_signal=from_signal,
            to_signal=None,
        )
    if present_from and present_to and from_signal != to_signal:
        return ClaimDelta(
            claim_id=claim_id,
            statement=statement,
            change="status_changed",
            from_signal=from_signal,
            to_signal=to_signal,
        )
    return None


def _instrument_status(raw: object) -> str | None:
    if raw in {"result", "refuted", "undecided"}:
        return str(raw)
    return None


def collect_instrument_outcomes(
    *,
    interval_ids: list[UUID],
    checkpoints: dict[UUID, Checkpoint],
    claim_ids_by_checkpoint: dict[UUID, list[UUID]],
) -> list[InstrumentOutcome]:
    """Blame tuples on the directed interval, sorted for a stable payload."""
    outcomes: list[InstrumentOutcome] = []
    for checkpoint_id in interval_ids:
        checkpoint = checkpoints.get(checkpoint_id)
        if checkpoint is None:
            continue
        invocations = checkpoint.tool_invocations or []
        claim_ids = claim_ids_by_checkpoint.get(checkpoint_id, [])
        for invocation in invocations:
            if not isinstance(invocation, dict):
                continue
            instrument = invocation.get("instrument")
            status_value = _instrument_status(invocation.get("status"))
            if not isinstance(instrument, str) or not instrument or status_value is None:
                continue
            outcomes.append(
                InstrumentOutcome(
                    checkpoint_id=checkpoint_id,
                    instrument=instrument,
                    status=status_value,  # type: ignore[arg-type]
                    claim_ids=list(claim_ids),
                    summary=checkpoint.summary,
                )
            )
    outcomes.sort(
        key=lambda row: (
            checkpoints[row.checkpoint_id].created_at,
            row.checkpoint_id,
            row.instrument,
        )
    )
    return outcomes


def _claim_present(
    *,
    claim: Claim,
    tip: Checkpoint,
    ancestor_ids: set[UUID],
    referenced_by: dict[UUID, set[UUID]],
    ever_referenced: set[UUID],
) -> bool:
    """Whether the claim is on the line at ``tip``.

    Referenced on an ancestor ⇒ on the line. Never referenced anywhere and
    created at or before the tip ⇒ a project-level fact that already existed.
    Referenced only on another line ⇒ not present here.
    """
    refs = referenced_by.get(claim.id, set())
    if refs & ancestor_ids:
        return True
    if claim.id not in ever_referenced and claim.created_at <= tip.created_at:
        return True
    return False


def _signal_at(
    claim_id: UUID,
    ancestor_ids: set[UUID],
    validations_by_claim: dict[UUID, list[ValidationRead]],
) -> ClaimSignal:
    visible = [
        row
        for row in validations_by_claim.get(claim_id, [])
        if row.recording_checkpoint_id is not None
        and row.recording_checkpoint_id in ancestor_ids
    ]
    return claim_service.compute_signal(visible)


def _grounding_at(
    claim_id: UUID,
    *,
    tip: Checkpoint,
    ancestor_ids: set[UUID],
    links_by_claim: dict[UUID, list[tuple[UUID, str, str, dict[str, Any] | None, datetime]]],
    recorded_evidence: dict[UUID, set[UUID]],
) -> ClaimGrounding:
    """Evidence-axis snapshot at ``tip``.

    Each link is ``(evidence_id, relation_kind, source_type, metadata, created_at)``.
    Evidence recorded on an ancestor checkpoint counts; hand-attached evidence
    (never recorded on any checkpoint) counts when ``created_at <= tip``.
    """
    rows: list[tuple[str, str, dict[str, Any] | None]] = []
    for evidence_id, relation_kind, source_type, metadata, created_at in links_by_claim.get(
        claim_id, []
    ):
        recorders = recorded_evidence.get(evidence_id, set())
        if recorders:
            if recorders & ancestor_ids:
                rows.append((relation_kind, source_type, metadata))
            continue
        if created_at <= tip.created_at:
            rows.append((relation_kind, source_type, metadata))
    return grounding_service.compute_grounding(rows)


async def _require_project(db: AsyncSession, project_id: UUID) -> Project:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )
    return project


async def _latest_on_branch(db: AsyncSession, branch_id: UUID) -> Checkpoint | None:
    result = await db.execute(
        select(Checkpoint)
        .where(Checkpoint.branch_id == branch_id)
        .order_by(Checkpoint.created_at.desc(), Checkpoint.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _latest_main_line(db: AsyncSession, project_id: UUID) -> Checkpoint | None:
    result = await db.execute(
        select(Checkpoint)
        .where(Checkpoint.project_id == project_id, Checkpoint.branch_id.is_(None))
        .order_by(Checkpoint.created_at.desc(), Checkpoint.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _unknown(value: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=_UNKNOWN_REF.format(value=value),
    )


async def resolve_ref(db: AsyncSession, project_id: UUID, raw: str) -> ResolvedRef:
    """Resolve a client token onto a checkpoint in ``project_id``.

    Grammar, in order:

    1. UUID of a checkpoint, tag, or branch in this project.
    2. ``main`` / ``mainline`` / ``@main`` / ``HEAD`` → main-line tip.
    3. Exact tag name (unique per project).
    4. Exact branch name.

    A tag named the same as a branch wins (names collide rarely; tags are the
    named *commit*). Unknown → ``404``, no writes.
    """
    value = raw.strip()
    if not value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="from/to ref must not be empty",
        )

    try:
        uid = UUID(value)
    except ValueError:
        uid = None

    if uid is not None:
        checkpoint = await db.get(Checkpoint, uid)
        if checkpoint is not None and checkpoint.project_id == project_id:
            return ResolvedRef(
                input=value,
                kind="checkpoint",
                checkpoint_id=checkpoint.id,
                branch_id=checkpoint.branch_id,
                label=checkpoint.summary,
            )
        tag = await db.get(Tag, uid)
        if tag is not None and tag.project_id == project_id:
            return ResolvedRef(
                input=value,
                kind="tag",
                checkpoint_id=tag.checkpoint_id,
                tag_id=tag.id,
                label=tag.name,
            )
        branch = await db.get(Branch, uid)
        if branch is not None and branch.project_id == project_id:
            tip = await _latest_on_branch(db, branch.id)
            if tip is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"branch {branch.name} has no checkpoints",
                )
            return ResolvedRef(
                input=value,
                kind="branch",
                checkpoint_id=tip.id,
                branch_id=branch.id,
                label=branch.name,
            )
        raise _unknown(value)

    if value.lower() in _MAIN_ALIASES:
        tip = await _latest_main_line(db, project_id)
        if tip is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="main line has no checkpoints",
            )
        return ResolvedRef(
            input=value,
            kind="main",
            checkpoint_id=tip.id,
            label="main",
        )

    tag_row = (
        await db.execute(select(Tag).where(Tag.project_id == project_id, Tag.name == value))
    ).scalar_one_or_none()
    if tag_row is not None:
        return ResolvedRef(
            input=value,
            kind="tag",
            checkpoint_id=tag_row.checkpoint_id,
            tag_id=tag_row.id,
            label=tag_row.name,
        )

    branch_row = (
        await db.execute(
            select(Branch).where(Branch.project_id == project_id, Branch.name == value)
        )
    ).scalar_one_or_none()
    if branch_row is not None:
        tip = await _latest_on_branch(db, branch_row.id)
        if tip is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"branch {branch_row.name} has no checkpoints",
            )
        return ResolvedRef(
            input=value,
            kind="branch",
            checkpoint_id=tip.id,
            branch_id=branch_row.id,
            label=branch_row.name,
        )

    raise _unknown(value)


async def _load_parent_map(
    db: AsyncSession, checkpoint_ids: list[UUID]
) -> dict[UUID, list[UUID]]:
    parent_map: dict[UUID, list[UUID]] = {cid: [] for cid in checkpoint_ids}
    if not checkpoint_ids:
        return parent_map
    rows = await db.execute(
        select(checkpoint_parent.c.checkpoint_id, checkpoint_parent.c.parent_id).where(
            checkpoint_parent.c.checkpoint_id.in_(checkpoint_ids)
        )
    )
    for child_id, parent_id in rows:
        parent_map.setdefault(child_id, []).append(parent_id)
    for parents in parent_map.values():
        parents.sort()
    return parent_map


async def semantic_diff(
    db: AsyncSession,
    project_id: UUID,
    from_raw: str,
    to_raw: str,
) -> SemanticDiffRead:
    """Compare two tips. Read-only — callers must not commit around this."""
    await _require_project(db, project_id)
    from_ref = await resolve_ref(db, project_id, from_raw)
    to_ref = await resolve_ref(db, project_id, to_raw)

    checkpoints_result = await db.execute(
        select(Checkpoint).where(Checkpoint.project_id == project_id)
    )
    checkpoints = {row.id: row for row in checkpoints_result.scalars()}
    created_at = {cid: ckpt.created_at for cid, ckpt in checkpoints.items()}
    parent_map = await _load_parent_map(db, list(checkpoints))

    from_anc = walk_ancestors(from_ref.checkpoint_id, parent_map)
    to_anc = walk_ancestors(to_ref.checkpoint_id, parent_map)
    from_only = from_anc - to_anc
    to_only = to_anc - from_anc
    merge_base_id = lowest_common_ancestor(from_anc, to_anc, parent_map, created_at)
    ancestry = Ancestry(
        from_is_ancestor_of_to=from_ref.checkpoint_id in to_anc
        and from_ref.checkpoint_id != to_ref.checkpoint_id,
        to_is_ancestor_of_from=to_ref.checkpoint_id in from_anc
        and from_ref.checkpoint_id != to_ref.checkpoint_id,
        diverged=bool(from_only and to_only),
        merge_base_id=merge_base_id,
        interval_checkpoint_ids=sort_checkpoint_ids(to_only, created_at),
        from_only_checkpoint_ids=sort_checkpoint_ids(from_only, created_at),
        to_only_checkpoint_ids=sort_checkpoint_ids(to_only, created_at),
    )
    # Same tip is an ancestor of itself; the flags above exclude equality so
    # "A is an ancestor of A" does not read as movement.
    if from_ref.checkpoint_id == to_ref.checkpoint_id:
        ancestry = Ancestry(
            from_is_ancestor_of_to=False,
            to_is_ancestor_of_from=False,
            diverged=False,
            merge_base_id=from_ref.checkpoint_id,
            interval_checkpoint_ids=[],
            from_only_checkpoint_ids=[],
            to_only_checkpoint_ids=[],
        )

    checkpoint_ids = list(checkpoints)
    if checkpoint_ids:
        refs_result = await db.execute(
            select(CheckpointRef).where(CheckpointRef.checkpoint_id.in_(checkpoint_ids))
        )
        refs = list(refs_result.scalars())
    else:
        refs = []

    referenced_by: dict[UUID, set[UUID]] = defaultdict(set)
    ever_referenced: set[UUID] = set()
    recorded_evidence: dict[UUID, set[UUID]] = defaultdict(set)
    recording_validation: dict[UUID, UUID] = {}
    claim_ids_by_checkpoint: dict[UUID, list[UUID]] = defaultdict(list)
    for ref in refs:
        if ref.target_type == "claim":
            referenced_by[ref.target_id].add(ref.checkpoint_id)
            ever_referenced.add(ref.target_id)
            if ref.role == "evidenced":
                claim_ids_by_checkpoint[ref.checkpoint_id].append(ref.target_id)
        elif ref.target_type == "evidence":
            recorded_evidence[ref.target_id].add(ref.checkpoint_id)
        elif ref.target_type == "validation" and ref.role == "recorded":
            recording_validation.setdefault(ref.target_id, ref.checkpoint_id)

    for cid in claim_ids_by_checkpoint:
        claim_ids_by_checkpoint[cid] = sorted(set(claim_ids_by_checkpoint[cid]))

    claims = list(
        (await db.execute(select(Claim).where(Claim.project_id == project_id))).scalars()
    )
    claims.sort(key=lambda c: (c.created_at, c.id))

    validations = list(
        (
            await db.execute(select(Validation).where(Validation.project_id == project_id))
        ).scalars()
    )
    validations_by_claim: dict[UUID, list[ValidationRead]] = defaultdict(list)
    for row in validations:
        if row.claim_id is None:
            continue
        validations_by_claim[row.claim_id].append(
            ValidationRead(
                id=row.id,
                project_id=row.project_id,
                actor_id=row.actor_id,
                actor=None,
                target_type="claim",
                target_id=row.claim_id,
                outcome=row.outcome,
                notes=row.notes,
                recording_checkpoint_id=recording_validation.get(row.id),
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
        )
    for rows in validations_by_claim.values():
        rows.sort(key=lambda item: (item.created_at, item.id))

    link_rows = await db.execute(
        select(
            ClaimEvidenceLink.claim_id,
            ClaimEvidenceLink.evidence_id,
            ClaimEvidenceLink.relation_kind,
            Evidence.source_type,
            Evidence.evidence_metadata,
            Evidence.created_at,
        )
        .join(Evidence, Evidence.id == ClaimEvidenceLink.evidence_id)
        .where(Evidence.project_id == project_id)
    )
    links_by_claim: dict[
        UUID, list[tuple[UUID, str, str, dict[str, Any] | None, datetime]]
    ] = defaultdict(list)
    for claim_id, evidence_id, relation_kind, source_type, metadata, ev_created in link_rows:
        links_by_claim[claim_id].append(
            (evidence_id, relation_kind, source_type, metadata, ev_created)
        )

    from_tip = checkpoints[from_ref.checkpoint_id]
    to_tip = checkpoints[to_ref.checkpoint_id]

    claim_deltas: list[ClaimDelta] = []
    grounding_moves: list[GroundingMove] = []
    empty_grounding = ClaimGrounding()

    for claim in claims:
        present_from = _claim_present(
            claim=claim,
            tip=from_tip,
            ancestor_ids=from_anc,
            referenced_by=referenced_by,
            ever_referenced=ever_referenced,
        )
        present_to = _claim_present(
            claim=claim,
            tip=to_tip,
            ancestor_ids=to_anc,
            referenced_by=referenced_by,
            ever_referenced=ever_referenced,
        )
        from_signal = _signal_at(claim.id, from_anc, validations_by_claim)
        to_signal = _signal_at(claim.id, to_anc, validations_by_claim)
        delta = classify_claim_delta(
            claim_id=claim.id,
            statement=claim.statement,
            present_from=present_from,
            present_to=present_to,
            from_signal=from_signal,
            to_signal=to_signal,
        )
        if delta is not None:
            claim_deltas.append(delta)

        from_g = (
            _grounding_at(
                claim.id,
                tip=from_tip,
                ancestor_ids=from_anc,
                links_by_claim=links_by_claim,
                recorded_evidence=recorded_evidence,
            )
            if present_from
            else empty_grounding
        )
        to_g = (
            _grounding_at(
                claim.id,
                tip=to_tip,
                ancestor_ids=to_anc,
                links_by_claim=links_by_claim,
                recorded_evidence=recorded_evidence,
            )
            if present_to
            else empty_grounding
        )
        if present_from or present_to:
            yield_row = grounding_service.compute_yield(
                [claim.id], {claim.id: from_g}, {claim.id: to_g}
            )
            for moved in yield_row.changed:
                grounding_moves.append(
                    GroundingMove(
                        claim_id=moved.claim_id,
                        statement=claim.statement,
                        from_headline=moved.before,
                        to_headline=moved.after,
                        movement=moved.movement,
                    )
                )

    claim_deltas.sort(key=lambda row: row.claim_id)
    grounding_moves.sort(key=lambda row: row.claim_id)

    instruments = collect_instrument_outcomes(
        interval_ids=ancestry.interval_checkpoint_ids,
        checkpoints=checkpoints,
        claim_ids_by_checkpoint=claim_ids_by_checkpoint,
    )

    empty = not claim_deltas and not grounding_moves and not instruments
    return SemanticDiffRead(
        project_id=project_id,
        from_ref=from_ref,
        to_ref=to_ref,
        empty=empty,
        claims=claim_deltas,
        grounding=grounding_moves,
        instruments=instruments,
        ancestry=ancestry,
    )
