"""Agent-actor provisioning (0.12.0) — idempotency + the durable uniqueness guard (DB-backed).

Skips without ``TEST_DATABASE_URL``. The test schema is built from the ORM models
(``Base.metadata.create_all``), so the partial functional unique index declared on the ``Actor``
model is present here exactly as migration 0013 installs it in prod.
"""

from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.actor import Actor
from app.models.enums import ActorType
from app.services.agent_actors import (
    AGENT_ACTOR_DISPLAY_NAME,
    get_or_create_project_agent_actor,
)


async def test_get_or_create_is_idempotent(session_factory: async_sessionmaker) -> None:
    project_id = uuid4()

    async with session_factory() as session:
        first = await get_or_create_project_agent_actor(session, project_id)
        await session.commit()
        first_id = first.id
        assert first.type is ActorType.AGENT
        assert first.display_name == AGENT_ACTOR_DISPLAY_NAME
        assert first.account_id is None
        assert first.actor_metadata == {"project_id": str(project_id)}

    async with session_factory() as session:
        second = await get_or_create_project_agent_actor(session, project_id)
        await session.commit()
        assert second.id == first_id  # the same actor, not a second one


async def test_distinct_projects_get_distinct_agents(
    session_factory: async_sessionmaker,
) -> None:
    p1, p2 = uuid4(), uuid4()
    async with session_factory() as session:
        a1 = await get_or_create_project_agent_actor(session, p1)
        a2 = await get_or_create_project_agent_actor(session, p2)
        await session.commit()
        assert a1.id != a2.id


async def test_unique_index_blocks_a_second_agent_for_the_same_project(
    session_factory: async_sessionmaker,
) -> None:
    project_id = uuid4()
    async with session_factory() as session:
        await get_or_create_project_agent_actor(session, project_id)
        await session.commit()

    # A raw duplicate insert (bypassing the service's race guard) must be rejected by the partial
    # unique index — proving the DB-level idempotency guarantee, not just the app-level check.
    async with session_factory() as session:
        dup = Actor(
            type=ActorType.AGENT,
            display_name=AGENT_ACTOR_DISPLAY_NAME,
            account_id=None,
            actor_metadata={"project_id": str(project_id)},
        )
        session.add(dup)
        with pytest.raises(IntegrityError):
            await session.flush()
