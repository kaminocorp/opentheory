"""Killable subprocess wrapper for sync toolbench instruments (0.11.x Phase 2)."""

from __future__ import annotations

import multiprocessing
import queue
import time
from typing import Any

from app.toolbench.adapter import InstrumentResult
from app.toolbench.execution.errors import (
    ToolbenchExecutionError,
    ToolbenchMemoryExceeded,
    ToolbenchTimeout,
    ToolbenchWorkerError,
)
from app.toolbench.execution.policy import ExecutionLimits, subprocess_enabled
from app.toolbench.execution.worker import (
    child_exit_implies_memory_kill,
    envelope_to_result,
    run_instrument_in_child,
    run_instrument_in_thread,
)

TERMINATE_GRACE_S = 1.0
# How often the parent wakes to check liveness while blocking on the child's result. Reading the
# result *concurrently* with execution (not only after join) is what keeps a large result from
# wedging the child's exit: a full OS pipe blocks the Queue feeder thread, which blocks process
# exit, which a join-first runner would misread as a wall-clock timeout.
_RESULT_POLL_INTERVAL_S = 0.05
_TIMED_OUT = object()  # sentinel: wall budget elapsed before the child produced a result


def run_bounded_sync(
    instrument_name: str,
    inputs_dict: dict[str, Any],
    assumptions: dict[str, Any],
    limits: ExecutionLimits,
) -> InstrumentResult:
    """Run a sync instrument under wall-clock (and optional memory) caps.

    When ``subprocess_enabled()`` is False, executes in-thread for fast unit tests. Production
    keeps subprocess isolation enabled.
    """
    if not subprocess_enabled():
        return run_instrument_in_thread(instrument_name, inputs_dict, assumptions)
    return _run_in_subprocess(instrument_name, inputs_dict, assumptions, limits)


def _run_in_subprocess(
    instrument_name: str,
    inputs_dict: dict[str, Any],
    assumptions: dict[str, Any],
    limits: ExecutionLimits,
) -> InstrumentResult:
    ctx = multiprocessing.get_context("spawn")
    result_queue: multiprocessing.Queue = ctx.Queue()
    process = ctx.Process(
        target=run_instrument_in_child,
        args=(instrument_name, inputs_dict, assumptions),
        kwargs={
            "memory_limit_mb": limits.memory_limit_mb,
            "result_queue": result_queue,
        },
        name=f"toolbench-{instrument_name}",
    )

    started = time.monotonic()
    try:
        # start() sits inside the try so a spawn failure (rare — OSError under resource
        # exhaustion) still reaches the finally that closes the result queue, rather than leaking
        # its pipe fds until GC.
        process.start()
        envelope = _drain_result(process, result_queue, limits.wall_timeout_s)
        wall_ms = (time.monotonic() - started) * 1000

        if envelope is _TIMED_OUT:
            _terminate(process)
            raise ToolbenchTimeout(
                instrument_name=instrument_name,
                wall_ms=wall_ms,
                message="Instrument run exceeded resource limits (timed out)",
            )

        # The child has produced a result or exited; reap it so we can read the exit code and never
        # leave a zombie. A stubborn survivor (should not happen — the worker returns after put) is
        # force-killed.
        process.join(TERMINATE_GRACE_S)
        if process.is_alive():
            _terminate(process)

        if envelope is None:
            exit_code = process.exitcode
            if child_exit_implies_memory_kill(exit_code):
                raise ToolbenchMemoryExceeded(
                    instrument_name=instrument_name,
                    wall_ms=wall_ms,
                    message="Instrument run exceeded resource limits (memory)",
                )
            raise ToolbenchWorkerError(
                instrument_name=instrument_name,
                wall_ms=wall_ms,
                message=f"Child process failed (exit code {exit_code})",
            )

        try:
            return envelope_to_result(envelope, instrument_name=instrument_name)
        except (ValueError, ToolbenchExecutionError):
            # Instrument input error (ValueError) or a typed sandbox failure the worker tagged
            # (e.g. ToolbenchMemoryExceeded on an RLIMIT_AS MemoryError) — propagate as-is.
            raise
        except Exception as exc:
            raise ToolbenchWorkerError(
                instrument_name=instrument_name,
                wall_ms=wall_ms,
                message=str(exc),
            ) from exc
    finally:
        result_queue.close()


def _drain_result(
    process: multiprocessing.Process,
    result_queue: multiprocessing.Queue,
    wall_timeout_s: float,
) -> object:
    """Read the child's result envelope, draining the pipe *while* the child runs.

    Returns the envelope dict, ``None`` if the child exited without one (crash / external OOM kill),
    or :data:`_TIMED_OUT` if the wall budget elapsed first. Blocking on the queue (rather than
    joining first, then reading) is what lets an over-large result flow out of the child instead of
    deadlocking its exit; the short poll timeout only exists to notice an early, result-less death.
    """
    deadline = time.monotonic() + wall_timeout_s
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return _TIMED_OUT
        try:
            return result_queue.get(timeout=min(remaining, _RESULT_POLL_INTERVAL_S))
        except queue.Empty:
            if not process.is_alive():
                # Exited with nothing queued (or mid-flush): one last non-blocking read to cover the
                # put/exit race — child exit joins the feeder thread, so any put data is flushed —
                # then give up.
                try:
                    return result_queue.get_nowait()
                except queue.Empty:
                    return None
        except (EOFError, OSError):
            # The child died and closed the pipe write end — treat as a result-less exit; the caller
            # inspects the exit code (SIGKILL → memory) to classify it.
            return None


def _terminate(process: multiprocessing.Process) -> None:
    """SIGTERM then SIGKILL a still-running child, reaping it so no zombie survives."""
    if not process.is_alive():
        return
    process.terminate()
    process.join(TERMINATE_GRACE_S)
    if process.is_alive():
        process.kill()
        process.join(TERMINATE_GRACE_S)