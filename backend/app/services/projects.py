"""Project read services.

`get_project_overview` returns the project detail enriched with aggregate ledger counts
(0.3.4) so the workspace header can show the state of the ledger at a glance. Reads only;
the project create/list paths remain inline in the route.
"""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.checkpoint import Checkpoint
from app.models.claim import Claim
from app.models.evidence import Evidence
from app.models.project import Project
from app.models.thread import Thread
from app.schemas.project import ProjectCounts, ProjectOverview, ProjectRead


async def _count(db: AsyncSession, model: type, project_id: UUID) -> int:
    result = await db.execute(
        select(func.count()).select_from(model).where(model.project_id == project_id)
    )
    return int(result.scalar_one())


async def get_project_overview(db: AsyncSession, project_id: UUID) -> ProjectOverview:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    counts = ProjectCounts(
        threads=await _count(db, Thread, project_id),
        claims=await _count(db, Claim, project_id),
        evidence=await _count(db, Evidence, project_id),
        checkpoints=await _count(db, Checkpoint, project_id),
    )
    return ProjectOverview(**ProjectRead.model_validate(project).model_dump(), counts=counts)
