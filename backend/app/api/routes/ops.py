"""Perpetual ops dashboard — public ledger read (0.49.0).

``GET /projects/{id}/ops``. Always-on, mints nothing. Same posture as
semantic diff / blame and the project budget read: a derived snapshot
over append-only rows, not a write and not an instrument.
"""

from uuid import UUID

from fastapi import APIRouter

from app.api.deps import DbSession
from app.schemas.ops import ProjectOpsRead
from app.services import ops as ops_service

router = APIRouter()


@router.get(
    "/projects/{project_id}/ops",
    response_model=ProjectOpsRead,
    tags=["ops"],
)
async def get_project_ops(project_id: UUID, db: DbSession) -> ProjectOpsRead:
    return await ops_service.project_ops(db, project_id)
