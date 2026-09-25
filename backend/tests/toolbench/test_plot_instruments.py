"""Unit tests for Bench 6 ``plot.*`` — Vega-Lite specs, never proofs.

Pure in-process (no DB). Write-path / ``run_instrument`` round-trips live in
``test_instruments_write_path.py``.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from app.models.enums import ResultStatus
from app.toolbench.conformance import check_conformance
from app.toolbench.execution import limits_for, run_bounded_sync
from app.toolbench.instruments._plot_support import VEGA_LITE_SCHEMA, VIZ_NOTE
from app.toolbench.instruments._sympy_support import ENGINE, ENGINE_VERSION
from app.toolbench.instruments.plot_function import PLOT_FUNCTION
from app.toolbench.instruments.plot_points import PLOT_POINTS

_FUNCTION = {
    "expression": "x**2",
    "variable": "x",
    "domain_min": "-3",
    "domain_max": "3",
    "n_samples": 7,
}

_POINTS = {
    "points": [{"x": 0, "y": 0}, {"x": 1, "y": 1}, {"x": 2, "y": 4}],
    "mark": "point",
}


def _run(instrument: Any, inputs: dict[str, Any], assumptions: dict[str, Any] | None = None):
    validated = instrument.InputModel.model_validate(inputs)
    return instrument.run(validated, assumptions or {})


def test_plot_function_conforms() -> None:
    assert check_conformance(PLOT_FUNCTION, example_inputs=_FUNCTION) == []


def test_plot_points_conforms() -> None:
    assert check_conformance(PLOT_POINTS, example_inputs=_POINTS) == []


@pytest.mark.parametrize("instrument", (PLOT_FUNCTION, PLOT_POINTS))
def test_engine_is_pinned_to_sympy(instrument: Any) -> None:
    assert instrument.engine == ENGINE
    assert instrument.engine_version == ENGINE_VERSION
    assert instrument.version == "0.1.0"


def test_function_emits_a_vega_lite_spec() -> None:
    result = _run(PLOT_FUNCTION, _FUNCTION)
    assert result.status is ResultStatus.RESULT
    assert result.artifact_kind == "plot"
    assert result.output["approximate"] is True
    assert result.output["note"] == VIZ_NOTE
    assert result.output["n_plotted"] == 7
    spec = result.output["spec"]
    assert spec["$schema"] == VEGA_LITE_SCHEMA
    assert spec["mark"]["type"] == "line"
    assert len(spec["data"]["values"]) == 7
    # Endpoints of y = x^2 over [-3, 3].
    first, last = spec["data"]["values"][0], spec["data"]["values"][-1]
    assert first["x"] == pytest.approx(-3)
    assert first["y"] == pytest.approx(9)
    assert last["x"] == pytest.approx(3)
    assert last["y"] == pytest.approx(9)
    assert "Visualization only" in spec["description"]


def test_function_rejects_inverted_domain() -> None:
    with pytest.raises(ValueError, match="domain_min"):
        _run(
            PLOT_FUNCTION,
            {**_FUNCTION, "domain_min": "3", "domain_max": "-3"},
        )


def test_function_undecided_when_too_few_real_samples() -> None:
    # sqrt(x) over a fully-negative domain has no real samples.
    result = _run(
        PLOT_FUNCTION,
        {
            "expression": "sqrt(x)",
            "variable": "x",
            "domain_min": "-4",
            "domain_max": "-1",
            "n_samples": 8,
        },
    )
    assert result.status is ResultStatus.UNDECIDED
    assert result.artifact_kind == "plot"
    assert result.output["status_reason"] == "too_few_real_samples"
    assert result.output["n_plotted"] == 0
    # Never fabricate a curve.
    assert result.output["points"] == []


def test_function_accepts_symbolic_domain_endpoints() -> None:
    result = _run(
        PLOT_FUNCTION,
        {
            "expression": "sin(x)",
            "variable": "x",
            "domain_min": "0",
            "domain_max": "pi",
            "n_samples": 5,
        },
    )
    assert result.status is ResultStatus.RESULT
    assert result.output["domain"] == ["0", "pi"]
    assert result.output["points"][0]["x"] == pytest.approx(0)
    assert result.output["points"][-1]["x"] == pytest.approx(3.141592, rel=1e-4)


def test_points_scatter_spec() -> None:
    result = _run(PLOT_POINTS, _POINTS)
    assert result.status is ResultStatus.RESULT
    assert result.artifact_kind == "plot"
    assert result.output["approximate"] is True
    assert result.output["n_points"] == 3
    assert result.output["mark"] == "point"
    spec = result.output["spec"]
    assert spec["$schema"] == VEGA_LITE_SCHEMA
    assert spec["mark"]["type"] == "point"
    assert spec["data"]["values"] == [
        {"x": 0.0, "y": 0.0},
        {"x": 1.0, "y": 1.0},
        {"x": 2.0, "y": 4.0},
    ]


def test_points_line_from_exact_strings() -> None:
    result = _run(
        PLOT_POINTS,
        {
            "points": [{"x": "0", "y": "1/2"}, {"x": "1", "y": "sqrt(4)"}],
            "mark": "line",
        },
    )
    assert result.status is ResultStatus.RESULT
    assert result.output["mark"] == "line"
    assert result.output["points"][0]["y"] == pytest.approx(0.5)
    assert result.output["points"][1]["y"] == pytest.approx(2)


def test_points_line_needs_two_points() -> None:
    with pytest.raises(ValueError, match="at least two"):
        _run(PLOT_POINTS, {"points": [{"x": 0, "y": 0}], "mark": "line"})


def test_points_rejects_bad_mark() -> None:
    with pytest.raises(ValueError, match="mark"):
        _run(PLOT_POINTS, {**_POINTS, "mark": "heatmap"})


def test_points_rejects_empty() -> None:
    with pytest.raises(ValidationError):
        PLOT_POINTS.InputModel.model_validate({"points": []})


def test_plot_function_runs_through_the_killable_subprocess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "toolbench_subprocess_sandbox_enabled", True)
    limits = limits_for(PLOT_FUNCTION)
    result = run_bounded_sync("plot.function", _FUNCTION, {}, limits)
    assert result.status is ResultStatus.RESULT
    assert result.artifact_kind == "plot"
    assert result.output["n_plotted"] == 7
