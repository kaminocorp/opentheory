"""Phase 1 (0.11.1) — execution sandbox policy, settings, and error types.

DB-free. Proves configuration resolves correctly and per-instrument execution modes are honoured.
No behaviour change yet — the chokepoint is not wired until Phase 3.
"""

import pytest

from app.core.config import settings
from app.toolbench.execution import (
    ToolbenchBusy,
    ToolbenchExecutionError,
    ToolbenchMemoryExceeded,
    ToolbenchTimeout,
    ToolbenchWorkerError,
    execution_mode_for,
    limits_for,
    subprocess_enabled,
)
from app.toolbench.instruments import CALC_EVAL, OEIS_SEARCH


def test_settings_defaults():
    assert settings.toolbench_wall_timeout_s == 30.0
    assert settings.toolbench_memory_limit_mb == 0
    assert settings.toolbench_max_concurrent_runs == 2
    assert settings.toolbench_acquire_timeout_s == 5.0
    assert settings.toolbench_subprocess_sandbox_enabled is True


def test_limits_for_calc_eval_defaults():
    limits = limits_for(CALC_EVAL)
    assert limits.wall_timeout_s == 30.0
    assert limits.memory_limit_mb == 0
    assert limits.mode == "subprocess"
    assert limits.max_concurrent_runs == 2
    assert limits.acquire_timeout_s == 5.0


def test_limits_for_oeis_search_is_async():
    limits = limits_for(OEIS_SEARCH)
    assert limits.mode == "async"


def test_execution_mode_for_calc_eval():
    assert execution_mode_for(CALC_EVAL) == "subprocess"


def test_execution_mode_for_oeis_search():
    assert execution_mode_for(OEIS_SEARCH) == "async"


def test_limits_for_respects_settings_override(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "toolbench_wall_timeout_s", 12.5)
    monkeypatch.setattr(settings, "toolbench_memory_limit_mb", 128)
    monkeypatch.setattr(settings, "toolbench_max_concurrent_runs", 1)
    monkeypatch.setattr(settings, "toolbench_acquire_timeout_s", 2.0)

    limits = limits_for(CALC_EVAL)
    assert limits.wall_timeout_s == 12.5
    assert limits.memory_limit_mb == 128
    assert limits.max_concurrent_runs == 1
    assert limits.acquire_timeout_s == 2.0


def test_subprocess_enabled_reads_settings(monkeypatch: pytest.MonkeyPatch):
    assert subprocess_enabled() is True
    monkeypatch.setattr(settings, "toolbench_subprocess_sandbox_enabled", False)
    assert subprocess_enabled() is False


def test_error_types_carry_metadata():
    err = ToolbenchTimeout(instrument_name="calc.eval", wall_ms=30001.0)
    assert err.instrument_name == "calc.eval"
    assert err.reason == "timeout"
    assert err.wall_ms == 30001.0
    assert "calc.eval" in str(err)

    mem = ToolbenchMemoryExceeded(instrument_name="expr.compare")
    assert mem.reason == "memory"

    busy = ToolbenchBusy(instrument_name="geometry.coordinate_measure")
    assert busy.reason == "busy"

    worker = ToolbenchWorkerError(instrument_name="counterexample.search", message="child crashed")
    assert worker.reason == "worker_error"
    assert str(worker) == "child crashed"


def test_execution_error_is_exception_base():
    assert issubclass(ToolbenchTimeout, ToolbenchExecutionError)
    assert issubclass(ToolbenchMemoryExceeded, ToolbenchExecutionError)
    assert issubclass(ToolbenchBusy, ToolbenchExecutionError)
    assert issubclass(ToolbenchWorkerError, ToolbenchExecutionError)