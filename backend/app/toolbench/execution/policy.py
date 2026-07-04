"""Resolve execution limits and sandbox mode for toolbench instruments (0.11.x).

Phase 3 adds the concurrency semaphore used by the write-path chokepoint.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from inspect import iscoroutinefunction
from typing import Literal

from app.core.config import settings
from app.toolbench.adapter import Instrument
from app.toolbench.execution.errors import ToolbenchBusy

ExecutionMode = Literal["subprocess", "async"]


@dataclass(frozen=True, slots=True)
class ExecutionLimits:
    """Resolved caps for a single instrument run."""

    wall_timeout_s: float
    memory_limit_mb: int
    mode: ExecutionMode
    max_concurrent_runs: int
    acquire_timeout_s: float


def execution_mode_for(instrument: Instrument) -> ExecutionMode:
    """Dispatch mode from ``run``'s signature: ``async def`` → async, else subprocess.

    Deriving from the signature — the same predicate the write path dispatches on — keeps a single
    source of truth, so mode metadata and actual dispatch can never drift. A retrieval instrument
    (``oeis.search``) implements ``run`` as ``async def`` and runs on the event loop; every compute
    instrument is sync and runs in the killable subprocess.
    """
    return "async" if iscoroutinefunction(instrument.run) else "subprocess"


def limits_for(instrument: Instrument) -> ExecutionLimits:
    """Merge global settings with per-instrument execution mode."""
    return ExecutionLimits(
        wall_timeout_s=settings.toolbench_wall_timeout_s,
        memory_limit_mb=settings.toolbench_memory_limit_mb,
        mode=execution_mode_for(instrument),
        max_concurrent_runs=settings.toolbench_max_concurrent_runs,
        acquire_timeout_s=settings.toolbench_acquire_timeout_s,
    )


def subprocess_enabled() -> bool:
    """Whether sync compute instruments should run in a killable child process."""
    return settings.toolbench_subprocess_sandbox_enabled


_run_slot_semaphore: asyncio.Semaphore | None = None


def _get_run_slot_semaphore() -> asyncio.Semaphore:
    """Lazy-init the concurrency semaphore from ``toolbench_max_concurrent_runs``."""
    global _run_slot_semaphore
    if _run_slot_semaphore is None:
        count = settings.toolbench_max_concurrent_runs
        if count < 1:
            msg = "toolbench_max_concurrent_runs must be at least 1"
            raise ValueError(msg)
        _run_slot_semaphore = asyncio.Semaphore(count)
    return _run_slot_semaphore


def reset_run_slot_semaphore() -> None:
    """Clear the lazy semaphore — for tests that change concurrency settings."""
    global _run_slot_semaphore
    _run_slot_semaphore = None


@asynccontextmanager
async def acquire_run_slot(*, instrument_name: str) -> AsyncIterator[None]:
    """Hold one instrument-run slot; raise ``ToolbenchBusy`` when capacity is exhausted."""
    semaphore = _get_run_slot_semaphore()
    try:
        await asyncio.wait_for(
            semaphore.acquire(),
            timeout=settings.toolbench_acquire_timeout_s,
        )
    except TimeoutError as exc:
        raise ToolbenchBusy(
            instrument_name=instrument_name,
            message="Server busy — too many concurrent instrument runs",
        ) from exc
    try:
        yield
    finally:
        semaphore.release()