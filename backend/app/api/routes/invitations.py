from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import ActingActor, DbSession
from app.schemas.invitation import InvitationCreate, InvitationRead
from app.services import invitations as invitation_service
from app.services import project_members as member_service

# Invitations span two path families — project-scoped (/projects/{id}/invitations, owner/admin) and
# invitee-scoped (/me/invitations, /invitations/{id}/accept|decline) — so, like threads/funding,
# this router mounts at the root and declares full paths itself.
router = APIRouter()


# --- Project-side (owner/admin) ---------------------------------------------


@router.post(
    "/projects/{project_id}/invitations",
    response_model=InvitationRead,
    status_code=status.HTTP_201_CREATED,
    tags=["invitations"],
)
async def create_invitation(
    project_id: UUID,
    payload: InvitationCreate,
    db: DbSession,
    actor: ActingActor,
) -> InvitationRead:
    """Invite an existing account (by ``@username`` or email) — owner/admin only.

    ``ensure_can_manage`` gates this (unauth → ``401``, non-member → ``403``, missing → ``404``) and
    returns the locked project; the service resolves the identifier (``404`` if unknown) and rejects
    self / already-member / already-pending with ``409``.
    """
    project = await member_service.ensure_can_manage(db, project_id, actor)
    return await invitation_service.invite(db, project, payload.identifier, payload.role, actor)


@router.get(
    "/projects/{project_id}/invitations",
    response_model=list[InvitationRead],
    tags=["invitations"],
)
async def list_project_invitations(
    project_id: UUID, db: DbSession, actor: ActingActor
) -> list[InvitationRead]:
    """The project's outstanding (pending) invitations — owner/admin only."""
    project = await member_service.ensure_can_manage(db, project_id, actor)
    return await invitation_service.list_for_project(db, project, actor)


@router.delete(
    "/projects/{project_id}/invitations/{invitation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["invitations"],
)
async def revoke_invitation(
    project_id: UUID, invitation_id: UUID, db: DbSession, actor: ActingActor
) -> None:
    """Revoke a pending invitation — owner/admin only. ``204`` (no body), like member removal."""
    project = await member_service.ensure_can_manage(db, project_id, actor)
    await invitation_service.revoke(db, project, invitation_id, actor)


# --- Invitee-side (the bell inbox) ------------------------------------------


@router.get("/me/invitations", response_model=list[InvitationRead], tags=["invitations"])
async def my_invitations(db: DbSession, actor: ActingActor) -> list[InvitationRead]:
    """The caller's own pending invitations (drives the bell inbox). ``401`` if unauthenticated."""
    return await invitation_service.my_pending(db, actor)


@router.post(
    "/invitations/{invitation_id}/accept",
    response_model=InvitationRead,
    tags=["invitations"],
)
async def accept_invitation(
    invitation_id: UUID, db: DbSession, actor: ActingActor
) -> InvitationRead:
    """Accept an invitation addressed to you → become a member. Invitee-only (``403`` otherwise)."""
    return await invitation_service.accept(db, invitation_id, actor)


@router.post(
    "/invitations/{invitation_id}/decline",
    response_model=InvitationRead,
    tags=["invitations"],
)
async def decline_invitation(
    invitation_id: UUID, db: DbSession, actor: ActingActor
) -> InvitationRead:
    """Decline an invitation addressed to you. Invitee-only (``403`` otherwise)."""
    return await invitation_service.decline(db, invitation_id, actor)
