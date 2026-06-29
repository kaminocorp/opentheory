"""Project membership + authorization service (0.8.1).

The project-level analog of ``core.roles`` / ``require_internal``: ``ensure_can_manage`` is the
single gate every project-management write composes with. Authorization is keyed on the **account**
(the principal, 0.7.0) — an actor manages a project iff its owning account holds a ``ProjectMember``
row for that project. Account-less actors (``system`` / dev-bootstrap) have no principal and can
never manage.

Status codes (matching the rest of the API): unauthenticated → ``401`` (handled upstream by the
``ActingActor`` dependency, before this service runs); missing project → ``404``; signed-in
non-member (or, for owner-only actions, a mere admin) → ``403``.

Membership is access control, **not** intellectual credit — it lives in its own table and never
touches Contribution / Validation / FundingAllocation (the funder/contributor/validator separation).
"""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.actor import Actor
from app.models.enums import ProjectRole
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.schemas.account import AccountSummary
from app.schemas.project import ProjectMemberRead


async def _get_project_or_404(db: AsyncSession, project_id: UUID) -> Project:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


async def _membership(
    db: AsyncSession, project_id: UUID, account_id: UUID
) -> ProjectMember | None:
    result = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.account_id == account_id,
        )
    )
    return result.scalar_one_or_none()


async def ensure_can_manage(
    db: AsyncSession,
    project_id: UUID,
    actor: Actor,
    *,
    require_owner: bool = False,
) -> Project:
    """Authorize ``actor`` to manage ``project_id``; return the loaded project.

    Raises ``404`` if the project is missing, ``403`` if the actor's account is not a member (or,
    when ``require_owner``, not the ``OWNER``). An account-less actor is always ``403`` — it has no
    principal that can hold membership. The project is returned so the caller (e.g. the ``PATCH``
    handler) can mutate it without a second load.

    The project row is locked ``FOR UPDATE`` for the rest of the transaction. Every management
    *write* composes with this gate, so the lock serializes concurrent owner-mutating requests on
    the same project: without it, two interleaved transactions can each pass the Python owner-floor
    guards (``remove_member`` / ``set_member_role``) against a *stale* role read and drive the
    project to **zero** owners. The ``uq_project_one_owner`` partial index bounds owners at ≤1, but
    nothing at the DB level floors them at ≥1 — this lock is what makes the check-then-act atomic.
    """
    # One locking read replaces the plain fetch — no extra round-trip.
    result = await db.execute(select(Project).where(Project.id == project_id).with_for_update())
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    # Account-less actors (system / dev-bootstrap) hold no membership — never manage.
    if actor.account_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to manage this project",
        )

    member = await _membership(db, project_id, actor.account_id)
    if member is None or (require_owner and member.role != ProjectRole.OWNER):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to manage this project",
        )
    return project


async def list_members(db: AsyncSession, project_id: UUID) -> list[ProjectMemberRead]:
    """Public member list (id + handle + role), owner first then by join time.

    Returns the privacy-safe ``AccountSummary`` only — never email/roles. One join, no N+1.
    """
    await _get_project_or_404(db, project_id)
    result = await db.execute(
        select(ProjectMember, Account)
        .join(Account, ProjectMember.account_id == Account.id)
        .where(ProjectMember.project_id == project_id)
    )
    rows = result.all()
    # Owner first, then by join time so the list is stable. Sorted in Python, not SQL: the
    # named-enum labels are ``OWNER``/``ADMIN``, so a DB ``ORDER BY role`` would surface ADMIN
    # first. The key encodes both ordering keys, so it fully determines the result — no N+1.
    rows = sorted(rows, key=lambda r: (r[0].role != ProjectRole.OWNER, r[0].created_at))
    return [
        ProjectMemberRead(
            account=AccountSummary.model_validate(account),
            role=member.role,
            created_at=member.created_at,
        )
        for member, account in rows
    ]


async def remove_member(
    db: AsyncSession, project: Project, account_id: UUID, actor: Actor
) -> None:
    """Owner-only: remove a member. The sole owner cannot be removed (would orphan the project).

    ``project`` is the already-authorized project from ``ensure_can_manage(require_owner=True)``.
    Commits the delete (ProjectMember is mutable — not append-only — so an ORM delete is permitted).
    """
    member = await _membership(db, project.id, account_id)
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    if member.role == ProjectRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove the project owner; transfer ownership first",
        )
    await db.delete(member)
    await db.commit()


async def set_member_role(
    db: AsyncSession,
    project: Project,
    account_id: UUID,
    role: ProjectRole,
    actor: Actor,
) -> ProjectMemberRead:
    """Owner-only: change a member's role, including transferring ownership.

    Transferring ``OWNER`` to another member demotes the prior owner to ``ADMIN`` **in the same
    transaction**, so the ``uq_project_one_owner`` partial index never sees two owners. ``actor`` is
    the current owner (already authorized upstream).
    """
    target = await _membership(db, project.id, account_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    # Demoting the current owner would orphan the project: zero owners → no one can ever run an
    # owner-only action again (including reassigning ownership), so the project's governance is
    # permanently stuck. The *only* way to stop being owner is a transfer — promote another member
    # to OWNER, which demotes the prior owner in the same txn (below). This mirrors
    # ``remove_member``'s sole-owner guard: ``uq_project_one_owner`` bounds owners at ≤1, but only
    # creation (one owner) and these two guards keep the count at ≥1.
    if target.role == ProjectRole.OWNER and role != ProjectRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot demote the project owner; transfer ownership to another member first",
        )

    try:
        if role == ProjectRole.OWNER and target.role != ProjectRole.OWNER:
            # Ownership transfer: demote the current owner first, and `flush` that UPDATE *before*
            # promoting the target. The ``uq_project_one_owner`` index is a plain (non-deferred)
            # unique index, so Postgres checks it per statement — emitting the promotion first would
            # briefly see two owners and raise. Flushing the demotion guarantees order within the
            # one txn.
            if actor.account_id is not None:
                current_owner = await _membership(db, project.id, actor.account_id)
                if current_owner is not None and current_owner.role == ProjectRole.OWNER:
                    current_owner.role = ProjectRole.ADMIN
                    db.add(current_owner)
                    await db.flush()

        target.role = role
        db.add(target)
        await db.commit()
    except IntegrityError as exc:
        # Belt-and-suspenders behind the ``ensure_can_manage`` row lock: should a concurrent
        # promote still trip ``uq_project_one_owner``, surface a clean 409 (retryable) rather than
        # a raw 500. Data stays correct — the index guarantees ≤1 owner regardless.
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ownership changed concurrently; please retry",
        ) from exc

    account = await db.get(Account, account_id)
    assert account is not None  # membership FK guarantees it
    return ProjectMemberRead(
        account=AccountSummary.model_validate(account),
        role=target.role,
        created_at=target.created_at,
    )
