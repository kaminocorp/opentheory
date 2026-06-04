from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.actor import Actor

DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_acting_actor(
    db: DbSession,
    x_dev_actor_id: Annotated[str | None, Header()] = None,
) -> Actor:
    """Resolve the acting actor from the ``X-Dev-Actor-Id`` header.

    There is no authentication in 0.3.x — every write carries the acting actor as a
    header that must resolve to an existing ``Actor`` row. Real identity arrives in
    0.6.0. Missing/malformed headers and unknown actor ids are rejected.
    """
    if x_dev_actor_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Dev-Actor-Id header is required",
        )
    try:
        actor_id = UUID(x_dev_actor_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Dev-Actor-Id must be a valid UUID",
        ) from exc

    actor = await db.get(Actor, actor_id)
    if actor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Acting actor not found",
        )
    return actor


ActingActor = Annotated[Actor, Depends(get_acting_actor)]
