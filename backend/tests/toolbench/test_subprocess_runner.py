"""Phase 2 (0.11.2) — subprocess runner with wall-clock timeout.

DB-free. Proves sync instruments run in a killable child and that the in-thread fallback works
when ``toolbench_subprocess_sandbox_enabled`` is False. The chokepoint is not wired until Phase 3.
"""

import time

import pytest

from app.core.config import settings
from app.models.enums import ResultStatus
from app.toolbench.execution import (
    ExecutionLimits,
    ToolbenchTimeout,
    limits_for,
    run_bounded_sync,
)
from app.toolbench.instruments import CALC_EVAL
from tests.toolbench.stubs import register_test_instruments

_DEFAULT_LIMITS = ExecutionLimits(
    wall_timeout_s=30.0,
    memory_limit_mb=0,
    mode="subprocess",
    max_concurrent_runs=2,
    acquire_timeout_s=5.0,
)


@pytest.fixture(autouse=True)
def _register_stubs():
    register_test_instruments()


def test_calc_eval_completes_in_subprocess():
    limits = limits_for(CALC_EVAL)
    result = run_bounded_sync(
        "calc.eval",
        {"expression": "2 + 2"},
        {},
        limits,
    )
    assert result.status is ResultStatus.RESULT
    assert result.output["value"] == "4"


def test_sleep_stub_times_out(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "toolbench_subprocess_sandbox_enabled", True)
    monkeypatch.setattr(settings, "toolbench_wall_timeout_s", 0.5)
    limits = limits_for(CALC_EVAL)
    limits = ExecutionLimits(
        wall_timeout_s=0.5,
        memory_limit_mb=limits.memory_limit_mb,
        mode=limits.mode,
        max_concurrent_runs=limits.max_concurrent_runs,
        acquire_timeout_s=limits.acquire_timeout_s,
    )

    started = time.monotonic()
    with pytest.raises(ToolbenchTimeout) as exc_info:
        run_bounded_sync("test.sleep", {"seconds": 2.0}, {}, limits)
    elapsed = time.monotonic() - started

    assert exc_info.value.instrument_name == "test.sleep"
    assert elapsed < 2.0


def test_in_thread_fallback_when_subprocess_disabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "toolbench_subprocess_sandbox_enabled", False)

    result = run_bounded_sync(
        "calc.eval",
        {"expression": "3**2 + 4**2"},
        {},
        _DEFAULT_LIMITS,
    )
    assert result.output["value"] == "25"


def test_large_output_completes_without_deadlock(monkeypatch: pytest.MonkeyPatch):
    """A result larger than the OS pipe buffer must drain, not be misread as a timeout.

    ~200 KB of output blocks the child's Queue feeder against a ~64 KB pipe, which blocks its exit;
    a join-before-read runner would time it out. The concurrent drain reads it under the wall cap.
    """
    monkeypatch.setattr(settings, "toolbench_subprocess_sandbox_enabled", True)

    started = time.monotonic()
    result = run_bounded_sync("test.blob", {"size": 200_000}, {}, _DEFAULT_LIMITS)
    elapsed = time.monotonic() - started

    assert result.status is ResultStatus.RESULT
    assert result.output["size"] == 200_000
    assert len(result.output["blob"]) == 200_000
    assert elapsed < _DEFAULT_LIMITS.wall_timeout_s  # completed, not timed out


def test_value_error_reraised_from_child():
    with pytest.raises(ValueError, match="Unknown instrument"):
        run_bounded_sync("test.nonexistent", {}, {}, _DEFAULT_LIMITS)


def test_invalid_inputs_reraised_as_value_error():
    with pytest.raises(ValueError):
        run_bounded_sync("test.sleep", {"seconds": -1}, {}, _DEFAULT_LIMITS)