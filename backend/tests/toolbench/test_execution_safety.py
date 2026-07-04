"""Phase 4 (0.11.4) — execution sandbox safety + flagship regression.

Proves timeout/OOM paths mint nothing, expensive inputs fail fast, flagship instruments complete
under default caps, and concurrency prefers 503 over unbounded overlap. Mostly DB-free; the
throwaway-Postgres gate is the full ``tests/toolbench/`` suite.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.models.actor import Actor
from app.models.enums import ActorType, ResultStatus
from app.services.tool_runs import run_instrument
from app.toolbench.execution import ToolbenchBusy, acquire_run_slot, execute_sync_instrument
from app.toolbench.execution.policy import reset_run_slot_semaphore
from app.toolbench.instruments import (
    CALC_EVAL,
    COORDINATE_MEASURE,
    COUNTEREXAMPLE_SEARCH,
    EXPR_COMPARE,
)
from app.toolbench.registry import registry
from tests.toolbench.stubs import SleepInstrument, register_test_instruments

_FLAGSHIP_CORNER = {
    "points": {"A": [0, 0], "B": [3, 0], "C": [3, 4]},
    "distances": [["A", "C"]],
    "angles": [["A", "B", "C"]],
}

_PINNED_FALSIFIER = {
    "relation": "d == a + b",
    "variables": {"a": {"min": 3, "max": 3}, "b": {"min": 4, "max": 4}, "d": {"min": 5, "max": 5}},
}

_MAX_SAMPLES_GRID = {
    "relation": "a + b + c == c + b + a",
    "variables": {
        "a": {"min": 1, "max": 50},
        "b": {"min": 1, "max": 50},
        "c": {"min": 1, "max": 3},
    },
    "max_samples": 5000,
}


class _RecordingSession:
    """Minimal async session stub — records ``add`` calls for mint-nothing assertions."""

    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        return None

    async def get(self, _model: type, _id: object) -> None:
        return None


@pytest.fixture
def sandbox_subprocess_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "toolbench_subprocess_sandbox_enabled", True)
    reset_run_slot_semaphore()


@pytest.fixture
def sleep_instrument() -> SleepInstrument:
    register_test_instruments()
    instrument = registry.get("test.sleep")
    assert instrument is not None
    return instrument  # type: ignore[return-value]


async def test_timeout_via_run_instrument_mints_nothing_db_free(
    sandbox_subprocess_on: None,
    sleep_instrument: SleepInstrument,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "toolbench_wall_timeout_s", 0.5)
    reset_run_slot_semaphore()

    actor = Actor(id=uuid4(), type=ActorType.HUMAN, display_name="Safety")
    session = _RecordingSession()

    with pytest.raises(HTTPException) as exc_info:
        await run_instrument(
            session,  # type: ignore[arg-type]
            uuid4(),
            sleep_instrument,
            actor,
            inputs={"seconds": 2.0},
        )

    assert exc_info.value.status_code == 422
    assert "Instrument run exceeded resource limits" in str(exc_info.value.detail)
    assert session.added == []


@pytest.mark.parametrize(
    ("instrument", "inputs", "status", "assert_output"),
    [
        (
            COORDINATE_MEASURE,
            _FLAGSHIP_CORNER,
            ResultStatus.RESULT,
            lambda out: out["distances"] == {"A-C": "5"}
            and out["angles"]["A-B-C"]["degrees"] == "90",
        ),
        (
            COUNTEREXAMPLE_SEARCH,
            _PINNED_FALSIFIER,
            ResultStatus.REFUTED,
            lambda out: out["witness_relation"] == "5 == 7",
        ),
        (
            CALC_EVAL,
            {"expression": "3**2 + 4**2 == 5**2"},
            ResultStatus.RESULT,
            lambda out: out["holds"] is True,
        ),
        (
            EXPR_COMPARE,
            {"left": "(a + b)**2", "right": "a**2 + b**2"},
            ResultStatus.UNDECIDED,
            lambda out: out["equivalent"] is None and out["difference"] == "2*a*b",
        ),
    ],
    ids=[
        "geometry.corner",
        "counterexample.pinned",
        "calc.eval.pythagorean",
        "expr.compare.binomial",
    ],
)
async def test_flagship_instruments_complete_under_default_sandbox(
    sandbox_subprocess_on: None,
    instrument: Any,
    inputs: dict[str, Any],
    status: ResultStatus,
    assert_output: Any,
) -> None:
    validated = instrument.InputModel.model_validate(inputs)
    outcome = await execute_sync_instrument(instrument, validated, {})
    assert outcome.result.status is status
    assert_output(outcome.result.output)
    assert outcome.resource_used["sandbox"] in ("subprocess", "in-thread")
    assert outcome.resource_used["wall_ms"] >= 0


async def test_expensive_factorial_fails_fast_under_sandbox(
    sandbox_subprocess_on: None,
) -> None:
    validated = CALC_EVAL.InputModel.model_validate({"expression": "factorial(50000)"})
    started = time.monotonic()
    with pytest.raises(ValueError, match="limit"):
        await asyncio.wait_for(
            execute_sync_instrument(CALC_EVAL, validated, {}),
            timeout=60,
        )
    assert time.monotonic() - started < 10


async def test_max_samples_grid_completes_under_sandbox(
    sandbox_subprocess_on: None,
) -> None:
    validated = COUNTEREXAMPLE_SEARCH.InputModel.model_validate(_MAX_SAMPLES_GRID)
    started = time.monotonic()
    outcome = await asyncio.wait_for(
        execute_sync_instrument(COUNTEREXAMPLE_SEARCH, validated, {}),
        timeout=60,
    )
    elapsed = time.monotonic() - started
    assert elapsed < 60
    result = outcome.result
    assert result.status is ResultStatus.RESULT
    assert result.output["found"] is False
    assert result.output["samples_tried"] == 5000  # capped before the 10_000-cell space exhausts
    assert result.output["truncated"] is True
    assert result.output["search_space"] == {"a": "1..50", "b": "1..50", "c": "1..3"}


async def test_concurrency_third_waiter_gets_busy_not_unbounded_overlap(
    sandbox_subprocess_on: None,
    sleep_instrument: SleepInstrument,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Third overlapping run gets ToolbenchBusy after acquire timeout (503 at API layer)."""
    monkeypatch.setattr(settings, "toolbench_max_concurrent_runs", 2)
    monkeypatch.setattr(settings, "toolbench_acquire_timeout_s", 0.5)
    reset_run_slot_semaphore()

    async def _run_with_slot() -> object:
        async with acquire_run_slot(instrument_name="test.sleep"):
            validated = sleep_instrument.InputModel.model_validate({"seconds": 1.0})
            outcome = await execute_sync_instrument(sleep_instrument, validated, {})
            return outcome.result

    results = await asyncio.gather(
        _run_with_slot(),
        _run_with_slot(),
        _run_with_slot(),
        return_exceptions=True,
    )

    successes = [r for r in results if not isinstance(r, BaseException)]
    busy = [r for r in results if isinstance(r, ToolbenchBusy)]

    assert len(successes) == 2
    assert len(busy) == 1