"""``plot.function`` — ``y = f(x)`` over a closed domain → Vega-Lite spec.

Sampling is numeric and **approximate**. The artifact is a Vega-Lite spec, not a
raster and not a proof. Missing / non-real samples that leave fewer than two
points are honest ``undecided``. A plot never contributes a grounding grade.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ResultStatus
from app.toolbench.adapter import InstrumentResult
from app.toolbench.instruments._plot_support import (
    ENGINE,
    ENGINE_VERSION,
    MAX_SAMPLES,
    MIN_SAMPLES,
    VIZ_NOTE,
    evalf_real,
    sample_function,
    vega_lite_spec,
)
from app.toolbench.instruments._sympy_support import (
    attach_latex,
    symbol_assumptions,
    to_latex,
)
from app.toolbench.instruments._table_support import COLUMN_NAME_RE


class PlotFunctionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expression: str = Field(
        min_length=1,
        max_length=1000,
        description=(
            "Exact expression in `variable`, e.g. 'x**2'. Sampled numerically for the plot."
        ),
    )
    variable: str = Field(default="x", min_length=1, max_length=16)
    domain_min: str = Field(
        min_length=1,
        max_length=100,
        description="Closed-interval left endpoint as exact math ('-3', '0', '-pi').",
    )
    domain_max: str = Field(
        min_length=1,
        max_length=100,
        description="Closed-interval right endpoint as exact math ('3', 'pi').",
    )
    n_samples: int = Field(default=50, ge=MIN_SAMPLES, le=MAX_SAMPLES)


class PlotFunctionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expression: str
    variable: str
    domain: list[str]
    n_samples: int
    n_plotted: int
    approximate: bool
    spec: dict[str, Any]
    points: list[dict[str, float]]
    note: str
    status_reason: str | None = None
    expression_latex: str | None = None


def _validate_variable(name: str) -> str:
    cleaned = name.strip()
    if not COLUMN_NAME_RE.match(cleaned):
        raise ValueError(f"variable {name!r} must be a Python-ish identifier")
    return cleaned


class PlotFunction:
    name = "plot.function"
    namespace = "plot"
    version = "0.1.0"
    engine = ENGINE
    engine_version = ENGINE_VERSION
    description = (
        "Graph y = f(x) over a closed domain as a Vega-Lite spec. Numeric sampling "
        "is approximate visualization — never Grade-A evidence, never a proof."
    )
    InputModel = PlotFunctionInput
    OutputModel = PlotFunctionOutput

    def run(self, inputs: PlotFunctionInput, assumptions: dict[str, Any]) -> InstrumentResult:
        variable = _validate_variable(inputs.variable)
        syms = symbol_assumptions(assumptions)
        lo = evalf_real(inputs.domain_min, syms)
        hi = evalf_real(inputs.domain_max, syms)
        if lo >= hi:
            raise ValueError("domain_min must be strictly less than domain_max")

        points = sample_function(
            inputs.expression,
            variable,
            lo,
            hi,
            inputs.n_samples,
            syms,
        )
        domain = [inputs.domain_min.strip(), inputs.domain_max.strip()]
        description = (
            f"y = {inputs.expression} over [{domain[0]}, {domain[1]}] — {VIZ_NOTE}"
        )
        spec = vega_lite_spec(
            description=description,
            points=points,
            mark="line",
            x_title=variable,
            y_title=inputs.expression,
        )
        reason = None
        if len(points) < MIN_SAMPLES:
            status = ResultStatus.UNDECIDED
            reason = "too_few_real_samples"
        else:
            status = ResultStatus.RESULT

        payload = PlotFunctionOutput(
            expression=inputs.expression,
            variable=variable,
            domain=domain,
            n_samples=inputs.n_samples,
            n_plotted=len(points),
            approximate=True,
            spec=spec,
            points=points,
            note=VIZ_NOTE,
            status_reason=reason,
        ).model_dump(mode="json")
        return InstrumentResult(
            output=attach_latex(payload, expression_latex=to_latex(inputs.expression, syms)),
            status=status,
            artifact_kind="plot",
        )


PLOT_FUNCTION = PlotFunction()
