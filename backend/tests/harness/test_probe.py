"""Probe skips live OpenRouter unless explicitly opted in with a runtime."""

from __future__ import annotations

import pytest

from app.harness.composition import VERSION
from app.harness.probe import (
    LIVE_FLAG,
    OPENROUTER_KEY_ENV,
    live_probe_skip_reason,
    run_probe,
)


def test_probe_always_asserts_composition() -> None:
    report = run_probe()
    assert report.composition == "ok"
    assert report.fixture == "ok"
    assert report.skipped_live is True
    assert LIVE_FLAG in report.live


def test_live_skips_without_flag() -> None:
    reason = live_probe_skip_reason(
        {OPENROUTER_KEY_ENV: "sk-test"},
        dsh_on_path=True,
        sdk_importable=True,
    )
    assert reason is not None
    assert LIVE_FLAG in reason


def test_live_skips_without_key() -> None:
    reason = live_probe_skip_reason(
        {LIVE_FLAG: "1"},
        dsh_on_path=True,
        sdk_importable=True,
    )
    assert reason is not None
    assert OPENROUTER_KEY_ENV in reason


def test_live_skips_without_runtime() -> None:
    reason = live_probe_skip_reason(
        {LIVE_FLAG: "1", OPENROUTER_KEY_ENV: "sk-test"},
        dsh_on_path=False,
        sdk_importable=False,
    )
    assert reason is not None
    assert "[harness]" in reason


def test_live_opt_in_with_runtime_is_not_implemented() -> None:
    """M0 must not invent a live gateway. Opt-in + runtime still refuses."""
    from app.harness import probe

    original = probe.live_probe_skip_reason

    def _never_skip(*_args: object, **_kwargs: object) -> None:
        return None

    probe.live_probe_skip_reason = _never_skip  # type: ignore[method-assign]
    try:
        with pytest.raises(RuntimeError, match="not implemented in 0.40.0"):
            run_probe()
    finally:
        probe.live_probe_skip_reason = original  # type: ignore[method-assign]
    assert VERSION == "0.1.5rc1"
