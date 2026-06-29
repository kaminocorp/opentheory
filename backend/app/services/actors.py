from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.actor import Actor
from app.schemas.actor import ActorCreate


async def create_actor(db: AsyncSession, payload: ActorCreate) -> Actor:
    # Dev/test bootstrap (route is dev-gated). `payload.model_dump()` carries the optional
    # `account_id`, so a dev actor can be linked to a bootstrap Account (e.g. an internal funder
    # built via POST /accounts) — that link is what makes `actor_is_internal` true for the dev
    # funding path. `external_id`/`roles` are no longer actor fields (they live on the Account).
    actor = Actor(**payload.model_dump())
    db.add(actor)
    await db.commit()
    await db.refresh(actor)
    return actor


async def list_actors(db: AsyncSession) -> list[Actor]:
    result = await db.execute(select(Actor).order_by(Actor.created_at.desc()))
    return list(result.scalars())
