"""Phase 5 (0.11.5) — ``resource_used`` on blame tuple + structured logging."""

from __future__ import annotations

import logging
from uuid import UUID

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import settings
from app.models.actor import Actor
from app.schemas.tool_invocation import ToolInvocation
from app.services.tool_runs import run_instrument
from app.toolbench.execution.policy import reset_run_slot_semaphore
from app.toolbench.instruments import CALC_EVAL
from tests.test_toolbench_provenance import _valid_invocation
from tests.toolbench.stubs import register_test_instruments


def test_tool_invocation_accepts_resource_used() -> None:
    ti = ToolInvocation(
        **_valid_invocation(  # type: ignore[arg-type]
            resource_used={"wall_ms": 12.5, "sandbox": "subprocess", "memory_limit_mb": 256},
        )
    )
    dumped = ti.model_dump(mode="json")
    assert dumped["resource_used"]["sandbox"] == "subprocess"


def test_tool_invocation_rejects_unknown_resource_used_keys() -> None:
    with pytest.raises(ValidationError, match="unknown keys"):
        ToolInvocation(
            **_valid_invocation(resource_used={"grade": "A"}),  # type: ignore[arg-type]
        )


async def test_successful_calc_eval_blame_tuple_carries_resource_used(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(settings, "toolbench_subprocess_sandbox_enabled", True)
    reset_run_slot_semaphore()
    caplog.set_level(logging.INFO)

    actor_resp = await client.post(
        "/api/v1/actors",
        json={"type": "human", "display_name": "Observer"},
    )
    assert actor_resp.status_code == 201
    actor_id = actor_resp.json()["id"]

    project_resp = await client.post(
        "/api/v1/projects",
        json={"title": "Obs", "slug": "exec-obs", "question": "Q?"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert project_resp.status_code == 201
    project_id = UUID(project_resp.json()["id"])

    async with session_factory() as session:
        actor = await session.get(Actor, UUID(actor_id))
        run = await run_instrument(
            session,
            project_id,
            CALC_EVAL,
            actor,
            inputs={"expression": "2 + 2"},
        )

    entry = run.checkpoint.tool_invocations[0]
    assert entry["resource_used"] is not None
    assert entry["resource_used"]["sandbox"] == "subprocess"
    assert entry["resource_used"]["wall_ms"] >= 0

    assert any(
        "instrument_run_complete" in record.message and "calc.eval" in record.message
        for record in caplog.records
    )


async def test_timeout_logs_warning_and_omits_resource_used(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    register_test_instruments()
    from app.toolbench.registry import registry

    sleep = registry.get("test.sleep")
    assert sleep is not None

    monkeypatch.setattr(settings, "toolbench_subprocess_sandbox_enabled", True)
    monkeypatch.setattr(settings, "toolbench_wall_timeout_s", 0.5)
    reset_run_slot_semaphore()
    caplog.set_level(logging.WARNING)

    actor_resp = await client.post(
        "/api/v1/actors",
        json={"type": "human", "display_name": "Timeout observer"},
    )
    assert actor_resp.status_code == 201
    actor_id = actor_resp.json()["id"]

    project_resp = await client.post(
        "/api/v1/projects",
        json={"title": "Timeout", "slug": "exec-obs-timeout", "question": "Q?"},
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
    assert any(
        "instrument_run_resource_limit" in record.message
        for record in caplog.records
    )