"""Project collaboration invitations (0.8.7).

The invite layer that sits one step before ``ProjectMember``: an owner/admin invites an existing
account (by ``@username`` or email) → the invitee accepts (minting the membership) or declines.

Authorization splits two ways:

- **Project-side** (invite / list / revoke) composes with ``project_members.ensure_can_manage`` in
  the route, so only an owner/admin reaches these — and the project row is locked ``FOR UPDATE``.
- **Invitee-side** (accept / decline) is keyed on the *invitation's* ``invitee_account_id``: a
  caller may only act on an invitation addressed to their own account (``403`` otherwise). There is
  no project-membership check here — accepting is precisely how a non-member *becomes* one.

Like membership, an invitation is access control / governance — **not** intellectual credit — so
accepting records **no** ``Contribution`` (only *creating* a project does). It composes with
``ProjectMember`` and never touches Contribution / Validation / FundingAllocation.
"""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.account import Account
from app.models.actor import Actor
from app.models.enums import InvitationStatus, ProjectRole
from app.models.project import Project
from app.models.project_invitation import ProjectInvitation
from app.models.project_member import ProjectMember
from app.schemas.account import AccountSummary
from app.schemas.invitation import InvitationRead
from app.services.account import resolve_account_by_identifier


def _to_read(
    invitation: ProjectInvitation,
    *,
    project_title: str,
    invitee: Account,
    inviter: Account | None,
) -> InvitationRead:
    """Compose the privacy-safe read model. ``invitee``/``inviter`` collapse to ``AccountSummary``
    (id + display_name + public ``@username``) — never email/roles — so it is safe to serve to the
    invitee, who is not a member yet."""
    return InvitationRead(
        id=invitation.id,
        project_id=invitation.project_id,
        project_title=project_title,
        role=invitation.role,
        status=invitation.status,
        invitee=AccountSummary.model_validate(invitee),
        invited_by=AccountSummary.model_validate(inviter) if inviter is not None else None,
        created_at=invitation.created_at,
        updated_at=invitation.updated_at,
    )


async def _load_invitation(
    db: AsyncSession, invitation_id: UUID, *, for_update: bool = False
) -> ProjectInvitation | None:
    """Load one invitation with its project + both account summaries eager-loaded.

    ``selectinload`` issues a constant number of follow-up queries (not N+1), and with the app's
    ``expire_on_commit=False`` the loaded relationships survive the later ``commit`` so the read
    model can be built without a post-commit lazy-load (which would raise under async).

    ``for_update`` locks the invitation row ``FOR UPDATE``. Every status-mutating path
    (accept / decline / revoke) takes this lock, so they serialize on the row and their
    check-then-act becomes atomic — without it a concurrent accept+revoke could leave a member
    minted against a ``REVOKED`` invitation, and a double-accept could race the
    ``uq_project_member`` insert into an unhandled ``500``. ``selectinload`` (not ``joinedload``)
    is what makes the lock safe to combine with eager loads: it fetches the related accounts in
    *separate* queries, so ``FOR UPDATE`` applies only to the ``project_invitations`` row and never
    to the nullable side of an outer join (which Postgres rejects).
    """
    stmt = (
        select(ProjectInvitation)
        .options(
            selectinload(ProjectInvitation.project),
            selectinload(ProjectInvitation.invitee),
            selectinload(ProjectInvitation.invited_by),
        )
        .where(ProjectInvitation.id == invitation_id)
    )
    if for_update:
        stmt = stmt.with_for_update()
    return (await db.execute(stmt)).scalar_one_or_none()


async def invite(
    db: AsyncSession,
    project: Project,
    identifier: str,
    role: ProjectRole,
    actor: Actor,
) -> InvitationRead:
    """Invite an existing account (resolved by ``@username`` or email) to ``project``.

    ``project`` is the already-authorized project from ``ensure_can_manage`` (owner *or* admin —
    admins may invite further admins, by decision). Errors: unknown identifier → ``404``; inviting
    yourself, an existing member, or someone who already has a pending invite → ``409``. Re-inviting
    a previously **declined/revoked** user is an *upsert* — the single ``(project, invitee)`` row is
    reset to ``PENDING`` (the ``uq_project_invitation`` constraint forbids a second row).
    """
    invitee = await resolve_account_by_identifier(db, identifier)
    if invitee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No account found for that @username or email",
        )
    if invitee.id == actor.account_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You cannot invite yourself",
        )

    already_member = (
        await db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project.id,
                ProjectMember.account_id == invitee.id,
            )
        )
    ).scalar_one_or_none()
    if already_member is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That account is already a member of this project",
        )

    existing = (
        await db.execute(
            select(ProjectInvitation).where(
                ProjectInvitation.project_id == project.id,
                ProjectInvitation.invitee_account_id == invitee.id,
            )
        )
    ).scalar_one_or_none()

    if existing is not None:
        if existing.status == InvitationStatus.PENDING:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="That account already has a pending invitation",
            )
        # Re-invite after a decline/revoke: reset the *same* row to PENDING (uq_project_invitation
        # forbids a second row), refreshing the role and the inviter provenance.
        existing.role = role
        existing.status = InvitationStatus.PENDING
        existing.invited_by_account_id = actor.account_id
        invitation = existing
    else:
        invitation = ProjectInvitation(
            project_id=project.id,
            invitee_account_id=invitee.id,
            role=role,
            status=InvitationStatus.PENDING,
            invited_by_account_id=actor.account_id,
        )
        db.add(invitation)

    await db.commit()
    # `actor.account` is eager-loaded by the ActingActor dependency; the invitee was just resolved.
    return _to_read(
        invitation, project_title=project.title, invitee=invitee, inviter=actor.account
    )


async def list_for_project(
    db: AsyncSession, project: Project, actor: Actor
) -> list[InvitationRead]:
    """Owner/admin: the project's outstanding (``PENDING``) invitations, newest first.

    ``project`` is already authorized in the route, so its title is in hand — only the two account
    summaries need loading.
    """
    stmt = (
        select(ProjectInvitation)
        .options(
            selectinload(ProjectInvitation.invitee),
            selectinload(ProjectInvitation.invited_by),
        )
        .where(
            ProjectInvitation.project_id == project.id,
            ProjectInvitation.status == InvitationStatus.PENDING,
        )
        .order_by(ProjectInvitation.created_at.desc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [
        _to_read(inv, project_title=project.title, invitee=inv.invitee, inviter=inv.invited_by)
        for inv in rows
    ]


async def my_pending(db: AsyncSession, actor: Actor) -> list[InvitationRead]:
    """The caller's own ``PENDING`` invitations (the bell inbox), newest first.

    An account-less actor (``system`` / dev) has no principal to receive invitations → empty list
    (a read, so no need to ``403`` — there is simply nothing to show).
    """
    if actor.account_id is None:
        return []
    stmt = (
        select(ProjectInvitation)
        .options(
            selectinload(ProjectInvitation.project),
            selectinload(ProjectInvitation.invitee),
            selectinload(ProjectInvitation.invited_by),
        )
        .where(
            ProjectInvitation.invitee_account_id == actor.account_id,
            ProjectInvitation.status == InvitationStatus.PENDING,
        )
        .order_by(ProjectInvitation.created_at.desc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [
        _to_read(
            inv, project_title=inv.project.title, invitee=inv.invitee, inviter=inv.invited_by
        )
        for inv in rows
    ]


def _require_invitee(invitation: ProjectInvitation, actor: Actor) -> None:
    """Authorize an invitee-side action: the actor's account must be the invitation's invitee."""
    if actor.account_id is None or invitation.invitee_account_id != actor.account_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This invitation is not addressed to you",
        )


async def accept(db: AsyncSession, invitation_id: UUID, actor: Actor) -> InvitationRead:
    """Invitee-only: accept a pending invitation → mint the ``ProjectMember`` + mark ``ACCEPTED``.

    One transaction, serialized by the invitation-row ``FOR UPDATE`` lock so the check-then-mint is
    atomic: a concurrent accept blocks, then re-reads the now-``ACCEPTED`` row and returns an
    idempotent success — never a duplicate ``ProjectMember`` nor a ``uq_project_member`` ``500`` —
    and a concurrent ``revoke`` on the same row can no longer interleave to leave a member minted
    against a revoked invitation. Re-accepting an already-``ACCEPTED`` invite is a no-op success; a
    non-pending (declined/revoked) invitation → ``409``.
    """
    invitation = await _load_invitation(db, invitation_id, for_update=True)
    if invitation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")
    _require_invitee(invitation, actor)

    if invitation.status == InvitationStatus.ACCEPTED:
        return _to_read(
            invitation,
            project_title=invitation.project.title,
            invitee=invitation.invitee,
            inviter=invitation.invited_by,
        )
    if invitation.status != InvitationStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This invitation is no longer pending",
        )

    existing_member = (
        await db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == invitation.project_id,
                ProjectMember.account_id == invitation.invitee_account_id,
            )
        )
    ).scalar_one_or_none()
    if existing_member is None:
        db.add(
            ProjectMember(
                project_id=invitation.project_id,
                account_id=invitation.invitee_account_id,
                role=invitation.role,
                invited_by_account_id=invitation.invited_by_account_id,
            )
        )
    invitation.status = InvitationStatus.ACCEPTED
    await db.commit()
    return _to_read(
        invitation,
        project_title=invitation.project.title,
        invitee=invitation.invitee,
        inviter=invitation.invited_by,
    )


async def decline(db: AsyncSession, invitation_id: UUID, actor: Actor) -> InvitationRead:
    """Invitee-only: decline a pending invitation → ``DECLINED`` (no membership created).

    Idempotent on an already-``DECLINED`` invite; a non-pending (accepted/revoked) one → ``409``.
    The row is kept (not deleted) so an owner/admin can re-invite by resetting it to ``PENDING``.
    Takes the same invitation-row ``FOR UPDATE`` lock as ``accept``/``revoke`` so every status
    transition on the row serializes.
    """
    invitation = await _load_invitation(db, invitation_id, for_update=True)
    if invitation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")
    _require_invitee(invitation, actor)

    if invitation.status == InvitationStatus.DECLINED:
        return _to_read(
            invitation,
            project_title=invitation.project.title,
            invitee=invitation.invitee,
            inviter=invitation.invited_by,
        )
    if invitation.status != InvitationStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This invitation is no longer pending",
        )

    invitation.status = InvitationStatus.DECLINED
    await db.commit()
    return _to_read(
        invitation,
        project_title=invitation.project.title,
        invitee=invitation.invitee,
        inviter=invitation.invited_by,
    )


async def revoke(
    db: AsyncSession, project: Project, invitation_id: UUID, actor: Actor
) -> None:
    """Owner/admin: revoke a pending invitation (``project`` already authorized in the route).

    ``404`` if the invitation is missing or belongs to a different project. Idempotent on an
    already-``REVOKED`` one; revoking an accepted/declined invitation → ``409`` (revoke does **not**
    un-member an accepted invitee — removing a member is ``DELETE /members``).

    Locks the invitation row ``FOR UPDATE`` (the same lock ``accept``/``decline`` take) so a revoke
    racing an accept serializes on the row instead of interleaving into a member minted against a
    revoked invitation. ``ensure_can_manage`` already holds the project-row lock upstream; this is
    the row-level lock the invitee-side paths actually contend on.
    """
    invitation = (
        await db.execute(
            select(ProjectInvitation)
            .where(ProjectInvitation.id == invitation_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if invitation is None or invitation.project_id != project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")

    if invitation.status == InvitationStatus.REVOKED:
        return
    if invitation.status != InvitationStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only a pending invitation can be revoked",
        )

    invitation.status = InvitationStatus.REVOKED
    await db.commit()
