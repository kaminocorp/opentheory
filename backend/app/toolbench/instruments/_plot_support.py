"""Shared Vega-Lite spec builders for Bench 6 (``plot.*``).

Plots are **optional visualization**. The artifact is a Vega-Lite JSON spec (not a
raster) plus the sampled points that went into it. Floats are expected and marked
``approximate: true``. A plot is never Grade-A evidence and never a proof.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from app.toolbench.instruments._sympy_support import ENGINE, ENGINE_VERSION, parse

VEGA_LITE_SCHEMA = "https://vega.github.io/schema/vega-lite/v5.json"
MAX_SAMPLES = 200
MIN_SAMPLES = 2
MAX_POINTS = 500
VIZ_NOTE = "Visualization only — not evidence. A plot does not prove or refute a claim."

PlotMark = Literal["point", "line"]


def vega_lite_spec(
    *,
    description: str,
    points: list[dict[str, float]],
    mark: PlotMark,
    x_title: str,
    y_title: str,
) -> dict[str, Any]:
    """A portable Vega-Lite v5 spec. The UI may render it; the ledger stores it."""
    mark_spec: dict[str, Any]
    if mark == "line":
        mark_spec = {"type": "line", "interpolate": "monotone"}
    else:
        mark_spec = {"type": "point"}
    return {
        "$schema": VEGA_LITE_SCHEMA,
        "description": description,
        "data": {"values": points},
        "mark": mark_spec,
        "encoding": {
            "x": {"field": "x", "type": "quantitative", "title": x_title},
            "y": {"field": "y", "type": "quantitative", "title": y_title},
        },
    }


def evalf_real(text: str, assumptions: dict[str, dict[str, bool]]) -> float:
    """Parse ``text`` and take a real float — plots are approximate by contract."""
    expr = parse(text, assumptions)
    value = expr.evalf()
    if not bool(getattr(value, "is_real", False)):
        raise ValueError(f"{text!r} is not a real value — cannot plot it")
    as_float = float(value)
    if as_float != as_float or as_float in (float("inf"), float("-inf")):
        raise ValueError(f"{text!r} is not a finite real — cannot plot it")
    return as_float


def sample_function(
    expression: str,
    variable: str,
    domain_min: float,
    domain_max: float,
    n_samples: int,
    assumptions: dict[str, dict[str, bool]],
) -> list[dict[str, float]]:
    """Sample ``expression`` over ``[domain_min, domain_max]``. Skips non-real points."""
    from sympy import Symbol

    expr = parse(expression, assumptions)
    var = Symbol(variable)
    if n_samples < MIN_SAMPLES:
        raise ValueError(f"n_samples must be at least {MIN_SAMPLES}")
    span = domain_max - domain_min
    points: list[dict[str, float]] = []
    for i in range(n_samples):
        x = domain_min + (span * i / (n_samples - 1))
        y_expr = expr.subs(var, x).evalf()
        if not bool(getattr(y_expr, "is_real", False)):
            continue
        y = float(y_expr)
        if y != y or y in (float("inf"), float("-inf")):
            continue
        points.append({"x": float(x), "y": y})
    return points


class PointIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: int | float | str
    y: int | float | str


def coerce_plot_scalar(value: int | float | str, assumptions: dict[str, dict[str, bool]]) -> float:
    if isinstance(value, bool):
        raise ValueError("boolean coordinates are not allowed")
    if isinstance(value, (int, float)):
        as_float = float(value)
        if as_float != as_float or as_float in (float("inf"), float("-inf")):
            raise ValueError("coordinate is not a finite real")
        return as_float
    return evalf_real(value.strip(), assumptions)


__all__ = [
    "ENGINE",
    "ENGINE_VERSION",
    "MAX_POINTS",
    "MAX_SAMPLES",
    "MIN_SAMPLES",
    "PointIn",
    "VEGA_LITE_SCHEMA",
    "VIZ_NOTE",
    "coerce_plot_scalar",
    "evalf_real",
    "sample_function",
    "vega_lite_spec",
]
