from fastapi import APIRouter, status

from app.api.deps import DbSession
from app.models.actor import Actor
from app.schemas.actor import ActorCreate, ActorRead
from app.services import actors as actor_service

router = APIRouter()


@router.post("", response_model=ActorRead, status_code=status.HTTP_201_CREATED)
async def create_actor(payload: ActorCreate, db: DbSession) -> Actor:
    return await actor_service.create_actor(db, payload)


@router.get("", response_model=list[ActorRead])
async def list_actors(db: DbSession) -> list[Actor]:
    return await actor_service.list_actors(db)
