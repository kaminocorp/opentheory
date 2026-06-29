"""Contribution recording.

A ``Contribution`` is the attribution/provenance record for a meaningful action. From
0.3.2, the four create flows (thread, claim, evidence, checkpoint) each auto-record one.

``record_contribution`` deliberately does **not** commit: it ``add``s the row to the
caller's session so the contribution shares the create's transaction. If the create
rolls back, no orphan contribution survives; if the contribution fails, the create is
rolled back with it.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.actor import Actor
from app.models.contribution import Contribution

# Actions recorded for the 0.3.x create flows. Plain strings (the column is VARCHAR(80)).
ACTION_CREATE_THREAD = "create_thread"
ACTION_CREATE_CLAIM = "create_claim"
ACTION_CREATE_EVIDENCE = "create_evidence"
ACTION_CREATE_CHECKPOINT = "create_checkpoint"
ACTION_VALIDATE = "validate"  # 0.4.1: recording a validation (through the checkpoint chokepoint)
ACTION_CREATE_BRANCH = "create_branch"  # 0.4.2: forking a branch from a checkpoint
ACTION_CLOSE_BRANCH = "close_branch"  # 0.4.2: closing a branch as dead-end/superseded
ACTION_FUND = "fund"  # 0.6.3: a funding allocation (contribution-only — NOT through a checkpoint)
ACTION_CREATE_PROJECT = "create_project"  # 0.8.1: originating a project (intellectual origination)


def record_contribution(
    db: AsyncSession,
    *,
    project_id: UUID,
    actor: Actor | None,
    action: str,
    target_type: str,
    target_id: UUID,
    checkpoint_id: UUID | None = None,
    funding_allocation_id: UUID | None = None,
    notes: str | None = None,
) -> Contribution:
    """Add a contribution to the session (no commit — the caller owns the transaction).

    A contribution references *either* a ``checkpoint_id`` (research events, recorded through
    the chokepoint) *or* a ``funding_allocation_id`` (funding events — Decision #3), via the
    matching FK on ``Contribution``. The two are alternatives; funding sets ``checkpoint_id=None``.
    """
    contribution = Contribution(
        project_id=project_id,
        actor_id=actor.id if actor is not None else None,
        checkpoint_id=checkpoint_id,
        funding_allocation_id=funding_allocation_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        notes=notes,
    )
    db.add(contribution)
    return contribution
