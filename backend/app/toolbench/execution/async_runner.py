"""Async instrument execution with wall-clock timeout (0.11.x Phase 3)."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from pydantic import BaseModel

from app.toolbench.adapter import Instrument, InstrumentResult
from app.toolbench.execution.errors import ToolbenchTimeout
from app.toolbench.execution.policy import ExecutionLimits, limits_for


async def run_bounded_async(
    instrument: Instrument,
    validated: BaseModel,
    assumptions: dict[str, Any],
    limits: ExecutionLimits | None = None,
) -> InstrumentResult:
    """Run an async retrieval instrument under the same wall-clock budget as sync compute."""
    resolved = limits or limits_for(instrument)
    started = time.monotonic()
    try:
        return await asyncio.wait_for(
            instrument.run(validated, assumptions),
            timeout=resolved.wall_timeout_s,
        )
    except TimeoutError as exc:
        wall_ms = (time.monotonic() - started) * 1000
        raise ToolbenchTimeout(
            instrument_name=instrument.name,
            wall_ms=wall_ms,
            message="Instrument run exceeded resource limits (timed out)",
        ) from exc