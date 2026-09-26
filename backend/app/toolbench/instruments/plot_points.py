"""``plot.points`` — scatter / line from computed points → Vega-Lite spec.

The artifact is a Vega-Lite spec built from caller-supplied points. Coordinates
may be numbers (floats allowed — this is viz) or exact strings that ``evalf``.
Never a grade. Never a proof.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ResultStatus
from app.toolbench.adapter import InstrumentResult
from app.toolbench.instruments._plot_support import (
    ENGINE,
    ENGINE_VERSION,
    MAX_POINTS,
    VIZ_NOTE,
    PointIn,
    coerce_plot_scalar,
    vega_lite_spec,
)
from app.toolbench.instruments._sympy_support import symbol_assumptions


class PlotPointsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    points: list[PointIn] = Field(min_length=1, max_length=MAX_POINTS)
    mark: str = Field(default="point", description="Vega-Lite mark: 'point' or 'line'.")
    x_title: str = Field(default="x", max_length=64)
    y_title: str = Field(default="y", max_length=64)


class PlotPointsOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    n_points: int
    mark: str
    approximate: bool
    spec: dict[str, Any]
    points: list[dict[str, float]]
    note: str
    x_title: str
    y_title: str


def _mark(raw: str) -> str:
    cleaned = raw.strip().lower()
    if cleaned not in {"point", "line"}:
        raise ValueError("mark must be 'point' or 'line'")
    if cleaned == "line":
        return "line"
    return "point"


class PlotPoints:
    name = "plot.points"
    namespace = "plot"
    version = "0.1.0"
    engine = ENGINE
    engine_version = ENGINE_VERSION
    description = (
        "Scatter or line from computed points as a Vega-Lite spec. Visualization "
        "only — never Grade-A evidence, never a proof."
    )
    InputModel = PlotPointsInput
    OutputModel = PlotPointsOutput

    def run(self, inputs: PlotPointsInput, assumptions: dict[str, Any]) -> InstrumentResult:
        mark = _mark(inputs.mark)
        if mark == "line" and len(inputs.points) < 2:
            raise ValueError("a line plot needs at least two points")
        syms = symbol_assumptions(assumptions)
        points = [
            {
                "x": coerce_plot_scalar(pt.x, syms),
                "y": coerce_plot_scalar(pt.y, syms),
            }
            for pt in inputs.points
        ]
        x_title = inputs.x_title.strip() or "x"
        y_title = inputs.y_title.strip() or "y"
        spec = vega_lite_spec(
            description=f"{mark} of {len(points)} points — {VIZ_NOTE}",
            points=points,
            mark=mark,  # type: ignore[arg-type]
            x_title=x_title,
            y_title=y_title,
        )
        payload = PlotPointsOutput(
            n_points=len(points),
            mark=mark,
            approximate=True,
            spec=spec,
            points=points,
            note=VIZ_NOTE,
            x_title=x_title,
            y_title=y_title,
        ).model_dump(mode="json")
        return InstrumentResult(
            output=payload,
            status=ResultStatus.RESULT,
            artifact_kind="plot",
        )


PLOT_POINTS = PlotPoints()
