from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ActingActor
from app.db.session import get_db
from app.models.project import Project
from app.schemas.project import (
    MemberRoleUpdate,
    ProjectCreate,
    ProjectMemberRead,
    ProjectOverview,
    ProjectRead,
    ProjectUpdate,
)
from app.services import project_members as member_service
from app.services import projects as project_service

router = APIRouter()
DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(payload: ProjectCreate, db: DbSession, actor: ActingActor) -> Project:
    # `actor` (ActingActor) gates the write: creating a project requires a verified actor. The
    # service (0.8.1) makes the creator's account the OWNER and records a `create_project`
    # Contribution — atomically with the insert.
    return await project_service.create_project(db, payload, actor)


@router.get("", response_model=list[ProjectRead])
async def list_projects(db: DbSession) -> list[Project]:
    result = await db.execute(select(Project).order_by(Project.created_at.desc()))
    return list(result.scalars())


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(project_id: UUID, db: DbSession) -> Project:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.get("/{project_id}/overview", response_model=ProjectOverview)
async def get_project_overview(project_id: UUID, db: DbSession) -> ProjectOverview:
    return await project_service.get_project_overview(db, project_id)


@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project(
    project_id: UUID, payload: ProjectUpdate, db: DbSession, actor: ActingActor
) -> Project:
    """Edit project metadata — owner/admin only (0.8.1).

    Authorization is enforced in the service (``ensure_can_manage``): unauthenticated → ``401``
    (the ``ActingActor`` dependency), signed-in non-member → ``403``, missing → ``404``. A partial
    update: only the fields the caller sends change. Plain in-place mutation — Project is not
    append-only, so a title fix is not a ledger event (no checkpoint).
    """
    project = await member_service.ensure_can_manage(db, project_id, actor)
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(project, field, value)
    await db.commit()
    await db.refresh(project)
    return project


@router.get("/{project_id}/members", response_model=list[ProjectMemberRead])
async def list_project_members(project_id: UUID, db: DbSession) -> list[ProjectMemberRead]:
    """Public member list (handles + roles). Privacy-safe (no email/roles)."""
    return await member_service.list_members(db, project_id)


@router.delete("/{project_id}/members/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_project_member(
    project_id: UUID, account_id: UUID, db: DbSession, actor: ActingActor
) -> None:
    """Remove a member — owner only. The sole owner cannot be removed."""
    project = await member_service.ensure_can_manage(db, project_id, actor, require_owner=True)
    await member_service.remove_member(db, project, account_id, actor)


@router.patch("/{project_id}/members/{account_id}", response_model=ProjectMemberRead)
async def update_project_member(
    project_id: UUID,
    account_id: UUID,
    payload: MemberRoleUpdate,
    db: DbSession,
    actor: ActingActor,
) -> ProjectMemberRead:
    """Change a member's role / transfer ownership — owner only. Body: ``{ "role": ... }``."""
    project = await member_service.ensure_can_manage(db, project_id, actor, require_owner=True)
    return await member_service.set_member_role(db, project, account_id, payload.role, actor)
