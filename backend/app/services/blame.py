"""Semantic research-git blame — derived read over one claim's ledger chain (0.36.0).

A ``git blame`` for research space: the ordered checkpoints, actors, and tool
invocations that produced or evidence-grounded a claim. Deterministic. Mints
nothing. Same claim → same payload.

A checkpoint *touches* the claim when any of these hold:

- a ``checkpoint_refs`` row targets the claim
- a ``checkpoint_refs`` row targets evidence linked to the claim
- a ``checkpoint_refs`` row records a validation of the claim

Ancestor walk is the same DAG closure semantic diff uses (self + parents,
merge nodes union every parent). State at a step is reconstructed from that
closure so signal / grounding movement is honest to the line, not a live
rewrite of ``Claim.status``.

Unknown project or claim → ``404``. The function never writes.
"""

from collections import defaultdict
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.actor import Actor
from app.models.agent_run import AgentRun
from app.models.checkpoint import Checkpoint
from app.models.claim import Claim
from app.models.contribution import Contribution
from app.models.evidence import Evidence
from app.models.links import CheckpointRef, ClaimEvidenceLink
from app.models.project import Project
from app.models.validation import Validation
from app.schemas.blame import (
    BlameActor,
    BlameAgentRun,
    BlameInstrument,
    BlameStep,
    ClaimBlameRead,
)
from app.schemas.claim import ClaimGrounding, ClaimSignal, GroundingHeadline
from app.schemas.validation import ValidationRead
from app.services import claims as claim_service
from app.services.diff import (
    _grounding_at,
    _instrument_status,
    _load_parent_map,
    _signal_at,
    sort_checkpoint_ids,
    walk_ancestors,
)

_UNKNOWN_CLAIM = "Claim {claim_id} not found"


def _opt_str(raw: object) -> str | None:
    if isinstance(raw, str) and raw:
        return raw
    return None


def classify_touch(
    *,
    checkpoint_id: UUID,
    claim_id: UUID,
    refs: list[tuple[UUID, str, UUID, str]],
    evidence_ids: set[UUID],
    validation_ids: set[UUID],
    has_instruments: bool,
) -> list[str] | None:
    """How this checkpoint touches the claim, or ``None`` if it does not.

    Pure. Roles are the raw ref roles for a claim target; ``evidence`` /
    ``validated`` for those target types; ``instrument`` when a well-formed
    blame tuple is also present on a touching checkpoint.
    """
    roles: set[str] = set()
    for ref_checkpoint_id, target_type, target_id, role in refs:
        if ref_checkpoint_id != checkpoint_id:
            continue
        if target_type == "claim" and target_id == claim_id:
            roles.add(role)
        elif target_type == "evidence" and target_id in evidence_ids:
            roles.add("evidence")
        elif target_type == "validation" and target_id in validation_ids:
            roles.add("validated")
    if not roles:
        return None
    if has_instruments:
        roles.add("instrument")
    return sorted(roles)


def collect_blame_instruments(invocations: list[object] | None) -> list[BlameInstrument]:
    """Well-formed blame tuples only; malformed entries are skipped, never invented."""
    rows: list[BlameInstrument] = []
    for invocation in invocations or []:
        if not isinstance(invocation, dict):
            continue
        instrument = invocation.get("instrument")
        status_value = _instrument_status(invocation.get("status"))
        if not isinstance(instrument, str) or not instrument or status_value is None:
            continue
        rows.append(
            BlameInstrument(
                instrument=instrument,
                status=status_value,  # type: ignore[arg-type]
                instrument_version=_opt_str(invocation.get("instrument_version")),
                engine=_opt_str(invocation.get("engine")),
                engine_version=_opt_str(invocation.get("engine_version")),
            )
        )
    rows.sort(key=lambda row: (row.instrument, row.status))
    return rows


def link_agent_run(
    checkpoint_id: UUID,
    runs: list[AgentRun],
) -> BlameAgentRun | None:
    """Newest agent pass whose step JSON names this checkpoint, or ``None``.

    Linkage is derived from ``AgentRun.steps[].checkpoint_id`` — no schema.
    Several passes can theoretically name the same id; the newest
    ``(created_at, id)`` wins so the payload stays deterministic.
    """
    matches: list[AgentRun] = []
    wanted = str(checkpoint_id)
    for run in runs:
        for step in run.steps or []:
            if not isinstance(step, dict):
                continue
            if step.get("checkpoint_id") == wanted:
                matches.append(run)
                break
    if not matches:
        return None
    matches.sort(key=lambda run: (run.created_at, run.id), reverse=True)
    run = matches[0]
    status_value = run.status.value if hasattr(run.status, "value") else str(run.status)
    return BlameAgentRun(
        id=run.id,
        role=run.role,
        model=run.model,
        status=status_value,
    )


def _empty_signal() -> ClaimSignal:
    return "none"


def _empty_headline() -> GroundingHeadline:
    return "ungrounded"


async def _require_project(db: AsyncSession, project_id: UUID) -> Project:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )
    return project


def _unknown_claim(claim_id: UUID) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=_UNKNOWN_CLAIM.format(claim_id=claim_id),
    )


async def blame_claim(
    db: AsyncSession,
    project_id: UUID,
    claim_id: UUID,
) -> ClaimBlameRead:
    """Return the claim's production chain. Read-only — callers must not commit."""
    await _require_project(db, project_id)
    claim = await db.get(Claim, claim_id)
    if claim is None or claim.project_id != project_id:
        raise _unknown_claim(claim_id)

    checkpoints_result = await db.execute(
        select(Checkpoint).where(Checkpoint.project_id == project_id)
    )
    checkpoints = {row.id: row for row in checkpoints_result.scalars()}
    created_at = {cid: ckpt.created_at for cid, ckpt in checkpoints.items()}
    parent_map = await _load_parent_map(db, list(checkpoints))

    checkpoint_ids = list(checkpoints)
    if checkpoint_ids:
        refs_result = await db.execute(
            select(CheckpointRef).where(CheckpointRef.checkpoint_id.in_(checkpoint_ids))
        )
        refs = list(refs_result.scalars())
    else:
        refs = []

    ref_tuples: list[tuple[UUID, str, UUID, str]] = [
        (ref.checkpoint_id, ref.target_type, ref.target_id, ref.role) for ref in refs
    ]

    recorded_evidence: dict[UUID, set[UUID]] = defaultdict(set)
    recording_validation: dict[UUID, UUID] = {}
    for ref in refs:
        if ref.target_type == "evidence":
            recorded_evidence[ref.target_id].add(ref.checkpoint_id)
        elif ref.target_type == "validation" and ref.role == "recorded":
            recording_validation.setdefault(ref.target_id, ref.checkpoint_id)

    validations = list(
        (
            await db.execute(
                select(Validation).where(
                    Validation.project_id == project_id,
                    Validation.claim_id == claim_id,
                )
            )
        ).scalars()
    )
    validation_ids = {row.id for row in validations}
    validations_by_claim: dict[UUID, list[ValidationRead]] = {claim_id: []}
    for row in validations:
        validations_by_claim[claim_id].append(
            ValidationRead(
                id=row.id,
                project_id=row.project_id,
                actor_id=row.actor_id,
                actor=None,
                target_type="claim",
                target_id=claim_id,
                outcome=row.outcome,
                notes=row.notes,
                recording_checkpoint_id=recording_validation.get(row.id),
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
        )
    validations_by_claim[claim_id].sort(key=lambda item: (item.created_at, item.id))

    link_rows = await db.execute(
        select(
            ClaimEvidenceLink.evidence_id,
            ClaimEvidenceLink.relation_kind,
            Evidence.source_type,
            Evidence.evidence_metadata,
            Evidence.created_at,
        )
        .join(Evidence, Evidence.id == ClaimEvidenceLink.evidence_id)
        .where(ClaimEvidenceLink.claim_id == claim_id)
    )
    evidence_ids: set[UUID] = set()
    links_by_claim: dict[
        UUID, list[tuple[UUID, str, str, dict[str, Any] | None, datetime]]
    ] = {claim_id: []}
    for evidence_id, relation_kind, source_type, metadata, ev_created in link_rows:
        evidence_ids.add(evidence_id)
        links_by_claim[claim_id].append(
            (evidence_id, relation_kind, source_type, metadata, ev_created)
        )

    touching: dict[UUID, list[str]] = {}
    instruments_by_checkpoint: dict[UUID, list[BlameInstrument]] = {}
    for checkpoint_id, checkpoint in checkpoints.items():
        instruments = collect_blame_instruments(checkpoint.tool_invocations)
        instruments_by_checkpoint[checkpoint_id] = instruments
        roles = classify_touch(
            checkpoint_id=checkpoint_id,
            claim_id=claim_id,
            refs=ref_tuples,
            evidence_ids=evidence_ids,
            validation_ids=validation_ids,
            has_instruments=bool(instruments),
        )
        if roles is not None:
            touching[checkpoint_id] = roles

    ordered_ids = sort_checkpoint_ids(set(touching), created_at)

    author_ids = {
        checkpoints[cid].author_id
        for cid in ordered_ids
        if checkpoints[cid].author_id is not None
    }
    authors: dict[UUID, Actor] = {}
    if author_ids:
        author_rows = await db.execute(select(Actor).where(Actor.id.in_(author_ids)))
        authors = {row.id: row for row in author_rows.scalars()}

    contribution_kind: dict[UUID, str] = {}
    if ordered_ids:
        contrib_rows = await db.execute(
            select(Contribution).where(Contribution.checkpoint_id.in_(ordered_ids))
        )
        for row in contrib_rows.scalars():
            if row.checkpoint_id is None:
                continue
            # Several contributions can share a checkpoint in theory; first by
            # (created_at, id) wins so the kind is stable.
            existing = contribution_kind.get(row.checkpoint_id)
            if existing is None:
                contribution_kind[row.checkpoint_id] = row.action

    agent_runs: list[AgentRun] = []
    if ordered_ids:
        run_rows = await db.execute(
            select(AgentRun).where(AgentRun.project_id == project_id)
        )
        agent_runs = list(run_rows.scalars())

    empty_grounding = ClaimGrounding()
    chain: list[BlameStep] = []
    for checkpoint_id in ordered_ids:
        checkpoint = checkpoints[checkpoint_id]
        ancestor_ids = walk_ancestors(checkpoint_id, parent_map)
        before_ids = ancestor_ids - {checkpoint_id}
        parents = list(parent_map.get(checkpoint_id, ()))
        parents.sort()

        signal_after = _signal_at(claim_id, ancestor_ids, validations_by_claim)
        grounding_after = _grounding_at(
            claim_id,
            tip=checkpoint,
            ancestor_ids=ancestor_ids,
            links_by_claim=links_by_claim,
            recorded_evidence=recorded_evidence,
        )
        if before_ids:
            # Any ancestor works as the "tip" timestamp for hand-attached
            # evidence; pick the newest so created_at alignment stays honest.
            before_tip_id = sort_checkpoint_ids(before_ids, created_at)[-1]
            before_tip = checkpoints[before_tip_id]
            signal_before = _signal_at(claim_id, before_ids, validations_by_claim)
            grounding_before = _grounding_at(
                claim_id,
                tip=before_tip,
                ancestor_ids=before_ids,
                links_by_claim=links_by_claim,
                recorded_evidence=recorded_evidence,
            )
        else:
            signal_before = _empty_signal()
            grounding_before = empty_grounding

        signal_moved = signal_before != signal_after
        grounding_moved = grounding_before.headline != grounding_after.headline

        author_row = authors.get(checkpoint.author_id) if checkpoint.author_id else None
        author = (
            BlameActor(
                id=author_row.id,
                display_name=author_row.display_name,
                type=author_row.type,
            )
            if author_row is not None
            else None
        )

        chain.append(
            BlameStep(
                checkpoint_id=checkpoint_id,
                created_at=checkpoint.created_at,
                summary=checkpoint.summary,
                stage=checkpoint.stage,
                branch_id=checkpoint.branch_id,
                parent_ids=parents,
                author=author,
                contribution_kind=contribution_kind.get(checkpoint_id),
                roles=touching[checkpoint_id],
                instruments=instruments_by_checkpoint.get(checkpoint_id, []),
                agent_run=link_agent_run(checkpoint_id, agent_runs),
                signal_after=signal_after,
                grounding_after=grounding_after.headline,
                signal_moved=signal_moved,
                grounding_moved=grounding_moved,
                from_signal=signal_before if signal_moved else None,
                from_grounding=grounding_before.headline if grounding_moved else None,
            )
        )

    current = await claim_service.get_claim(db, claim_id)
    return ClaimBlameRead(
        project_id=project_id,
        claim_id=claim_id,
        statement=claim.statement,
        thread_id=claim.thread_id,
        empty=len(chain) == 0,
        current_signal=current.signal,
        current_grounding=current.grounding.headline,
        chain=chain,
        checkpoint_ids=ordered_ids,
    )
