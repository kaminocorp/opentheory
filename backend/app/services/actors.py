from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.actor import Actor
from app.schemas.actor import ActorCreate


async def create_actor(db: AsyncSession, payload: ActorCreate) -> Actor:
    actor = Actor(**payload.model_dump())
    db.add(actor)
    await db.commit()
    await db.refresh(actor)
    return actor


async def list_actors(db: AsyncSession) -> list[Actor]:
    result = await db.execute(select(Actor).order_by(Actor.created_at.desc()))
    return list(result.scalars())
