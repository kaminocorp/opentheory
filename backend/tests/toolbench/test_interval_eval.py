"""Unit tests for ``interval.eval`` — proven enclosures + each honest outcome.

Pure in-process (no DB). Write-path / ``run_instrument`` round-trips live in
``test_instruments_write_path.py``.
"""

from __future__ import annotations

from fractions import Fraction
from typing import Any

import pytest
from pydantic import ValidationError

from app.models.enums import ResultStatus
from app.toolbench.conformance import check_conformance
from app.toolbench.execution import limits_for, run_bounded_sync
from app.toolbench.instruments._interval_support import (
    ENGINE,
    ENGINE_ARB,
    ENGINE_VERSION,
    METHOD_ARB,
    enclose,
    flint_available,
)
from app.toolbench.instruments.interval_eval import INTERVAL_EVAL

_SQRT2 = {"expression": "sqrt(2)"}
_PI = {"expression": "pi"}
_EXACT_SUM = {"expression": "1/3 + 1/6"}
_EQ_MISS = {"expression": "sqrt(2) == 2"}
_EQ_OVERLAP = {"expression": "sqrt(2) == sqrt(2)"}
_EQ_EXACT = {"expression": "2 + 2 == 4"}
_INEQ = {"expression": "pi > 3"}


def _run(inputs: dict[str, Any], assumptions: dict[str, Any] | None = None):
    validated = INTERVAL_EVAL.InputModel.model_validate(inputs)
    return INTERVAL_EVAL.run(validated, assumptions or {})


# --- conformance ---------------------------------------------------------------------------------


def test_interval_eval_conforms() -> None:
    assert check_conformance(INTERVAL_EVAL, example_inputs=_SQRT2) == []


def test_engine_pin_is_honest() -> None:
    assert INTERVAL_EVAL.engine == ENGINE
    assert INTERVAL_EVAL.engine_version == ENGINE_VERSION
    assert ENGINE_VERSION
    if flint_available():
        assert ENGINE == ENGINE_ARB


# --- behavioural: each honest outcome -------------------------------------------------------------


def test_sqrt2_is_a_proven_enclosure_not_a_float() -> None:
    result = _run(_SQRT2)
    assert result.status is ResultStatus.RESULT
    assert result.artifact_kind == "derivation"
    assert result.output["is_relation"] is False
    lo, hi = result.output["lo"], result.output["hi"]
    assert isinstance(lo, str) and isinstance(hi, str)
    assert "." not in lo or "/" in lo or lo.replace(".", "").replace("-", "").isdigit()
    # Never a Python float in the payload.
    assert not any(isinstance(v, float) for v in result.output.values())
    lo_f, hi_f = Fraction(lo), Fraction(hi)
    assert lo_f < hi_f
    # Tight Arb ball around √2: above 7/5, below 3/2, and it must straddle 99/70.
    assert lo_f > Fraction(7, 5)
    assert hi_f < Fraction(3, 2)
    assert lo_f < Fraction(99, 70) < hi_f or (lo_f < Fraction(15, 10) and hi_f > Fraction(14, 10))
    assert result.output["precision_bits"] == 64
    assert result.output["method"] in {METHOD_ARB, "mpmath.iv"}
    assert result.output.get("enclosure_latex")


def test_exact_rational_is_a_singleton() -> None:
    result = _run(_EXACT_SUM)
    assert result.status is ResultStatus.RESULT
    assert result.output["lo"] == result.output["hi"]
    assert Fraction(result.output["lo"]) == Fraction(1, 2)


def test_pi_enclosure_contains_22_over_7_on_one_side_only() -> None:
    result = _run(_PI)
    assert result.status is ResultStatus.RESULT
    lo, hi = Fraction(result.output["lo"]), Fraction(result.output["hi"])
    assert lo < Fraction(22, 7)
    assert hi < Fraction(22, 7)
    assert lo > 3


def test_relation_entirely_off_is_refuted() -> None:
    result = _run(_EQ_MISS)
    assert result.status is ResultStatus.REFUTED
    assert result.artifact_kind == "counterexample"
    assert result.output["holds"] is False
    assert result.output["is_relation"] is True
    assert Fraction(result.output["left_hi"]) < Fraction(result.output["right_lo"])


def test_relation_that_holds_strictly_is_result() -> None:
    result = _run(_INEQ)
    assert result.status is ResultStatus.RESULT
    assert result.output["holds"] is True
    assert result.artifact_kind == "derivation"


def test_exact_equality_of_singletons_is_result() -> None:
    result = _run(_EQ_EXACT)
    assert result.status is ResultStatus.RESULT
    assert result.output["holds"] is True


def test_overlapping_claimed_equality_is_undecided() -> None:
    """Two enclosures of the same irrational overlap — never a pretended equality."""
    result = _run(_EQ_OVERLAP)
    assert result.status is ResultStatus.UNDECIDED
    assert result.output["holds"] is None
    assert result.output["status_reason"] == "overlap"
    assert result.artifact_kind == "derivation"
    # Bounds are still recorded so a human can see the overlap.
    assert result.output["left_lo"] is not None
    assert result.output["right_lo"] is not None


def test_free_symbols_are_undecided() -> None:
    result = _run({"expression": "sqrt(x)"})
    assert result.status is ResultStatus.UNDECIDED
    assert result.output["lo"] is None
    assert result.output["status_reason"] == "free_symbols"


def test_non_real_is_undecided() -> None:
    result = _run({"expression": "sqrt(-1)"})
    assert result.status is ResultStatus.UNDECIDED
    assert result.output["status_reason"] in {"non_real", "domain"}
    assert result.output["lo"] is None


def test_timeout_budget_zero_is_undecided(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import settings

    original = settings.toolbench_interval_timeout_ms
    try:
        settings.toolbench_interval_timeout_ms = 0
        result = _run(_SQRT2)
    finally:
        settings.toolbench_interval_timeout_ms = original
    assert result.status is ResultStatus.UNDECIDED
    assert result.output["status_reason"] == "timeout"
    assert result.output["lo"] is None


def test_enclose_honours_elapsed_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.toolbench.instruments import _interval_support as support
    from app.toolbench.instruments._sympy_support import parse

    times = iter([0.0, 10.0])
    outcome = enclose(
        parse("sqrt(2)", {}),
        precision_bits=64,
        timeout_ms=5,
        now=lambda: next(times, 10.0),
    )
    assert outcome.kind == "undecided"
    assert outcome.reason == "timeout"
    assert support  # imported for the module under test


# --- input safety ---------------------------------------------------------------------------------


def test_run_rejects_float_literal() -> None:
    with pytest.raises(ValueError, match="float|decimal"):
        _run({"expression": "0.5"})


def test_run_rejects_injection() -> None:
    with pytest.raises(ValueError):
        _run({"expression": "__import__('os').getpid()"})


def test_run_rejects_assumptions() -> None:
    with pytest.raises(ValueError, match="does not accept assumptions"):
        _run(_SQRT2, {"x": {"positive": True}})


def test_input_rejects_precision_out_of_range() -> None:
    with pytest.raises(ValidationError):
        INTERVAL_EVAL.InputModel.model_validate({"expression": "2", "precision_bits": 8})
    with pytest.raises(ValidationError):
        INTERVAL_EVAL.InputModel.model_validate({"expression": "2", "precision_bits": 4096})


def test_run_is_synchronous() -> None:
    import inspect

    assert not inspect.iscoroutinefunction(INTERVAL_EVAL.run)


def test_interval_eval_runs_through_the_killable_subprocess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "toolbench_subprocess_sandbox_enabled", True)
    limits = limits_for(INTERVAL_EVAL)
    assert limits.mode == "subprocess"

    enclosed = run_bounded_sync("interval.eval", _SQRT2, {}, limits)
    assert enclosed.status is ResultStatus.RESULT
    assert enclosed.output["lo"] is not None
    assert enclosed.output["hi"] is not None

    refuted = run_bounded_sync("interval.eval", _EQ_MISS, {}, limits)
    assert refuted.status is ResultStatus.REFUTED
    assert refuted.output["holds"] is False

    with pytest.raises(ValueError, match="float|decimal"):
        run_bounded_sync("interval.eval", {"expression": "1.5"}, {}, limits)
