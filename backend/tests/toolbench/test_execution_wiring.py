"""Phase 3 (0.11.3) — execution sandbox wired through ``run_instrument``.

Concurrency and error-mapping tests are DB-free where possible; timeout + mint-nothing needs
Postgres.
"""

import asyncio
from uuid import UUID

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import settings
from app.models.actor import Actor
from app.models.artifact import Artifact
from app.models.checkpoint import Checkpoint
from app.services.tool_runs import run_instrument
from app.toolbench.execution import ToolbenchBusy, acquire_run_slot
from app.toolbench.execution.policy import reset_run_slot_semaphore
from app.toolbench.registry import registry
from tests.toolbench.stubs import register_test_instruments


async def test_acquire_run_slot_raises_busy_when_saturated(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "toolbench_max_concurrent_runs", 1)
    monkeypatch.setattr(settings, "toolbench_acquire_timeout_s", 0.2)
    reset_run_slot_semaphore()

    entered = asyncio.Event()
    release = asyncio.Event()

    async def _holder():
        async with acquire_run_slot(instrument_name="test.holder"):
            entered.set()
            await release.wait()

    holder = asyncio.create_task(_holder())
    await entered.wait()

    with pytest.raises(ToolbenchBusy):
        async with acquire_run_slot(instrument_name="test.waiter"):
            pass

    release.set()
    await holder


async def test_run_instrument_timeout_mints_nothing(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    register_test_instruments()
    sleep = registry.get("test.sleep")
    assert sleep is not None

    monkeypatch.setattr(settings, "toolbench_subprocess_sandbox_enabled", True)
    monkeypatch.setattr(settings, "toolbench_wall_timeout_s", 0.5)
    reset_run_slot_semaphore()

    actor_resp = await client.post(
        "/api/v1/actors",
        json={"type": "human", "display_name": "Timeout runner"},
    )
    assert actor_resp.status_code == 201
    actor_id = actor_resp.json()["id"]

    project_resp = await client.post(
        "/api/v1/projects",
        json={"title": "Timeout", "slug": "exec-timeout", "question": "Q?"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert project_resp.status_code == 201
    project_id = UUID(project_resp.json()["id"])

    async with session_factory() as session:
        actor = await session.get(Actor, UUID(actor_id))
        with pytest.raises(HTTPException) as exc_info:
            await run_instrument(
                session,
                project_id,
                sleep,
                actor,
                inputs={"seconds": 2.0},
            )

    assert exc_info.value.status_code == 422
    assert "Instrument run exceeded resource limits" in str(exc_info.value.detail)

    async with session_factory() as session:
        artifacts = (
            await session.execute(select(Artifact).where(Artifact.project_id == project_id))
        ).scalars().all()
        checkpoints = (
            await session.execute(
                select(Checkpoint).where(Checkpoint.project_id == project_id)
            )
        ).scalars().all()
        assert artifacts == []
        assert checkpoints == []