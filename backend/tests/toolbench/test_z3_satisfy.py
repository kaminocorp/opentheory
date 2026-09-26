"""Unit tests for ``z3.satisfy`` — model-finding + each honest outcome.

Pure in-process (no DB). Write-path / ``run_instrument`` round-trips live in
``test_instruments_write_path.py``.
"""

from __future__ import annotations

from fractions import Fraction
from typing import Any

import pytest
import z3
from pydantic import ValidationError

from app.models.enums import ResultStatus
from app.toolbench.conformance import check_conformance
from app.toolbench.execution import limits_for, run_bounded_sync
from app.toolbench.instruments._z3_support import ENGINE, ENGINE_VERSION, satisfy
from app.toolbench.instruments.z3_satisfy import Z3_SATISFY

# Concrete sat — two positives that sum to 1.
_SAT_INPUTS = {
    "variables": {"x": "real", "y": "real"},
    "constraints": ["x > 0", "y > 0", "x + y == 1"],
}

# Contradictory constraints — no model exists.
_UNSAT_INPUTS = {
    "variables": {"x": "real"},
    "constraints": ["x > 0", "x < 0"],
}


def _run(inputs: dict[str, Any], assumptions: dict[str, Any] | None = None):
    validated = Z3_SATISFY.InputModel.model_validate(inputs)
    return Z3_SATISFY.run(validated, assumptions or {})


# --- conformance ---------------------------------------------------------------------------------


def test_z3_satisfy_conforms() -> None:
    assert check_conformance(Z3_SATISFY, example_inputs=_SAT_INPUTS) == []


def test_engine_pin_is_z3() -> None:
    assert ENGINE == "z3"
    assert Z3_SATISFY.engine == "z3"
    assert Z3_SATISFY.engine_version == ENGINE_VERSION
    assert ENGINE_VERSION


# --- behavioural: each honest outcome -------------------------------------------------------------


def test_sat_returns_an_exact_model() -> None:
    result = _run(_SAT_INPUTS)
    assert result.status is ResultStatus.RESULT
    assert result.artifact_kind == "model"
    assert result.output["satisfied"] is True
    assert result.output["unsatisfiable"] is False
    assert result.output["certificate"] is None
    model = result.output["model"]
    assert model is not None
    assert set(model) == {"x", "y"}
    assert isinstance(model["x"], str)
    assert isinstance(model["y"], str)
    assert "." not in model["x"]
    assert "." not in model["y"]
    # Exact rationals — x>0, y>0, x+y=1. Never a float in the payload.
    assert not any(isinstance(v, float) for v in result.output.values())
    x = _as_rational(model["x"])
    y = _as_rational(model["y"])
    assert x > 0
    assert y > 0
    assert x + y == Fraction(1)


def test_unsat_is_refuted_never_a_model() -> None:
    result = _run(_UNSAT_INPUTS)
    assert result.status is ResultStatus.REFUTED
    assert result.artifact_kind == "proof"
    assert result.output["satisfied"] is False
    assert result.output["unsatisfiable"] is True
    assert result.output["model"] is None
    assert result.output["certificate"] == "unsat"
    used = result.output["used_constraints"]
    assert used is not None
    assert any("x > 0" in name for name in used)
    assert any("x < 0" in name for name in used)


def test_empty_constraints_are_trivially_sat() -> None:
    result = _run({"variables": {"x": "int"}, "constraints": []})
    assert result.status is ResultStatus.RESULT
    assert result.artifact_kind == "model"
    assert result.output["satisfied"] is True
    model = result.output["model"]
    assert model is not None
    assert set(model) == {"x"}
    assert isinstance(model["x"], str)


def test_nonlinear_unknown_is_honest_undecided() -> None:
    """A nonlinear fragment Z3 cannot settle → undecided, never a fake model.

    Tiny soft timeout so incompleteness/timeout is reliable. If Z3 *does* decide,
    sat/unsat are still accepted — the honesty bar is only that unknown never
    becomes a fabricated assignment.
    """
    from app.core.config import settings

    original = settings.toolbench_z3_timeout_ms
    try:
        settings.toolbench_z3_timeout_ms = 1
        result = _run(
            {
                "variables": {"x": "real", "y": "real"},
                "constraints": ["x*x + y*y == 1", "x*x*x + y*y*y == 1"],
            }
        )
    finally:
        settings.toolbench_z3_timeout_ms = original

    assert result.status in {
        ResultStatus.UNDECIDED,
        ResultStatus.RESULT,
        ResultStatus.REFUTED,
    }
    if result.status is ResultStatus.UNDECIDED:
        assert result.output["satisfied"] is False
        assert result.output["unsatisfiable"] is False
        assert result.output["model"] is None
        assert result.output["status_reason"] in {"timeout", "incomplete"}


def test_satisfy_timeout_maps_to_undecided_reason_timeout() -> None:
    """Direct harness: a 1ms budget on a hard check yields unknown → honest undecided."""
    x = z3.Int("x")
    y = z3.Int("y")
    outcome = satisfy(
        [("c0", x * x * x + y * y * y > 0)],
        env={"x": x, "y": y},
        timeout_ms=1,
    )
    if outcome.kind == "undecided":
        assert outcome.reason in {"timeout", "incomplete"}
        assert outcome.model is None
    else:
        assert outcome.kind in {"sat", "unsat"}


# --- translator / input safety (same bounds as z3.prove) ------------------------------------------


def test_run_rejects_float_in_constraint() -> None:
    with pytest.raises(ValueError, match="float|decimal|could not parse|unsupported"):
        _run({"variables": {"x": "real"}, "constraints": ["x > 0.5"]})


def test_run_rejects_undeclared_variable() -> None:
    with pytest.raises(ValueError, match="undeclared"):
        _run({"variables": {"x": "int"}, "constraints": ["x + y > 0"]})


def test_run_rejects_injection() -> None:
    with pytest.raises(ValueError):
        _run(
            {
                "variables": {"x": "int"},
                "constraints": ["x == __import__('os').getpid()"],
            }
        )


def test_run_rejects_assumptions() -> None:
    with pytest.raises(ValueError, match="does not accept assumptions"):
        _run(_SAT_INPUTS, {"x": {"positive": True}})


def test_input_rejects_blank_constraint() -> None:
    with pytest.raises(ValidationError):
        Z3_SATISFY.InputModel.model_validate(
            {"variables": {"x": "int"}, "constraints": ["   "]}
        )


def test_input_rejects_non_relation_constraint() -> None:
    with pytest.raises(ValidationError, match="relation or boolean formula"):
        Z3_SATISFY.InputModel.model_validate(
            {"variables": {"x": "int"}, "constraints": ["x + 1"]}
        )


def test_input_rejects_bad_variable_name() -> None:
    with pytest.raises(ValidationError):
        Z3_SATISFY.InputModel.model_validate(
            {"variables": {"x-y": "int"}, "constraints": ["x-y > 0"]}
        )


def test_latex_companions_present_on_sat() -> None:
    result = _run(_SAT_INPUTS)
    cl = result.output.get("constraints_latex")
    assert isinstance(cl, list)
    assert len(cl) == 3


def test_run_is_synchronous() -> None:
    import inspect

    assert not inspect.iscoroutinefunction(Z3_SATISFY.run)


def test_z3_satisfy_runs_through_the_killable_subprocess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "toolbench_subprocess_sandbox_enabled", True)
    limits = limits_for(Z3_SATISFY)
    assert limits.mode == "subprocess"

    sat = run_bounded_sync("z3.satisfy", _SAT_INPUTS, {}, limits)
    assert sat.status is ResultStatus.RESULT
    assert sat.artifact_kind == "model"
    assert sat.output["satisfied"] is True
    assert set(sat.output["model"]) == {"x", "y"}

    unsat = run_bounded_sync("z3.satisfy", _UNSAT_INPUTS, {}, limits)
    assert unsat.status is ResultStatus.REFUTED
    assert unsat.output["unsatisfiable"] is True
    assert unsat.output["model"] is None

    with pytest.raises(ValueError, match="undeclared"):
        run_bounded_sync(
            "z3.satisfy",
            {"variables": {"x": "int"}, "constraints": ["x + y > 0"]},
            {},
            limits,
        )


def _as_rational(text: str) -> Fraction:
    """Parse an exact int / ``p/q`` string for numeric checks — test helper only."""
    return Fraction(text)
