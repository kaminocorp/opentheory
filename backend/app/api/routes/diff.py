"""Semantic research-git diff — public ledger read (0.29.0).

``GET /projects/{id}/diff?from=&to=``. Always-on, mints nothing. Same posture as
checkpoint list / get: a derived read over the append-only graph, not a write
and not an instrument (instruments mint on ``result``).
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.schemas.diff import SemanticDiffRead
from app.services import diff as diff_service

router = APIRouter()


@router.get(
    "/projects/{project_id}/diff",
    response_model=SemanticDiffRead,
    tags=["diff"],
)
async def get_semantic_diff(
    project_id: UUID,
    db: DbSession,
    from_ref: Annotated[str, Query(alias="from", min_length=1)],
    to_ref: Annotated[str, Query(alias="to", min_length=1)],
) -> SemanticDiffRead:
    return await diff_service.semantic_diff(db, project_id, from_ref, to_ref)
