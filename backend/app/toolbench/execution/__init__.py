"""Toolbench execution sandbox — bounded, killable instrument runs (0.11.x).

Phase 3 wires sync subprocess isolation and async wall-clock caps through the write-path chokepoint.
"""

from app.toolbench.execution.async_runner import run_bounded_async
from app.toolbench.execution.errors import (
    ToolbenchBusy,
    ToolbenchExecutionError,
    ToolbenchMemoryExceeded,
    ToolbenchTimeout,
    ToolbenchWorkerError,
)
from app.toolbench.execution.outcome import ExecutionOutcome, build_resource_used
from app.toolbench.execution.policy import (
    ExecutionLimits,
    ExecutionMode,
    acquire_run_slot,
    execution_mode_for,
    limits_for,
    reset_run_slot_semaphore,
    subprocess_enabled,
)
from app.toolbench.execution.runner import (
    execute_async_instrument,
    execute_instrument,
    execute_sync_instrument,
)
from app.toolbench.execution.subprocess_runner import run_bounded_sync

__all__ = [
    "ExecutionLimits",
    "ExecutionMode",
    "ExecutionOutcome",
    "ToolbenchBusy",
    "ToolbenchExecutionError",
    "ToolbenchMemoryExceeded",
    "ToolbenchTimeout",
    "ToolbenchWorkerError",
    "acquire_run_slot",
    "build_resource_used",
    "execute_async_instrument",
    "execute_instrument",
    "execute_sync_instrument",
    "execution_mode_for",
    "limits_for",
    "reset_run_slot_semaphore",
    "run_bounded_async",
    "run_bounded_sync",
    "subprocess_enabled",
]