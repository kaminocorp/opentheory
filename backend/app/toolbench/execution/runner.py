"""High-level instrument execution entrypoints for the write path (0.11.x Phase 3+)."""

from __future__ import annotations

import time
from typing import Any

import anyio
from pydantic import BaseModel

from app.toolbench.adapter import Instrument
from app.toolbench.execution.async_runner import run_bounded_async
from app.toolbench.execution.outcome import ExecutionOutcome, build_resource_used
from app.toolbench.execution.policy import execution_mode_for, limits_for, subprocess_enabled
from app.toolbench.execution.subprocess_runner import run_bounded_sync as _run_bounded_sync_blocking


async def execute_instrument(
    instrument: Instrument,
    validated: BaseModel,
    assumptions: dict[str, Any],
) -> ExecutionOutcome:
    """Dispatch to the async or sync executor by the instrument's resolved execution mode.

    The single entrypoint for the write path — it does not need to know sync from async. The mode is
    derived once (:func:`execution_mode_for`, off ``run``'s signature) and both branches return an
    :class:`ExecutionOutcome`.
    """
    if execution_mode_for(instrument) == "async":
        return await execute_async_instrument(instrument, validated, assumptions)
    return await execute_sync_instrument(instrument, validated, assumptions)


async def execute_sync_instrument(
    instrument: Instrument,
    validated: BaseModel,
    assumptions: dict[str, Any],
) -> ExecutionOutcome:
    """Run a sync compute instrument off the event loop through the bounded subprocess wrapper."""
    limits = limits_for(instrument)
    sandbox = "in-thread" if not subprocess_enabled() else "subprocess"
    started = time.monotonic()
    result = await anyio.to_thread.run_sync(
        _run_bounded_sync_blocking,
        instrument.name,
        validated.model_dump(mode="json"),
        assumptions,
        limits,
    )
    wall_ms = (time.monotonic() - started) * 1000
    return ExecutionOutcome(
        result=result,
        resource_used=build_resource_used(wall_ms=wall_ms, sandbox=sandbox, limits=limits),
    )


async def execute_async_instrument(
    instrument: Instrument,
    validated: BaseModel,
    assumptions: dict[str, Any],
) -> ExecutionOutcome:
    """Run an async retrieval instrument on the event loop with ``asyncio.wait_for``."""
    limits = limits_for(instrument)
    started = time.monotonic()
    result = await run_bounded_async(instrument, validated, assumptions, limits)
    wall_ms = (time.monotonic() - started) * 1000
    return ExecutionOutcome(
        result=result,
        resource_used=build_resource_used(wall_ms=wall_ms, sandbox="async", limits=limits),
    )