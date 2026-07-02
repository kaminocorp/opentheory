"""``geometry.coordinate_measure`` — distances and angles between named points (the demo tool).

The flagship thread is *measuring across a corner*: given ``A=[0,0]``, ``B=[3,0]``, ``C=[3,4]`` it
reports ``dist(A,C) = 5`` and ``angle(A,B,C) = 90°`` — a human-runnable coordinate measurement, not
generic CAS. Everything is exact: integer/rational/symbolic coordinates flow through SymPy's
``Point``, so ``dist(A,C)`` is the integer ``5`` and the right angle is the exact ``pi/2`` (``90``
degrees), never a rounded float.

A measurement always ``result``s — it is not testing a claim, so ``refuted`` / ``undecided`` do not
arise here. The *assumptions* of the corner thread (``a > 0``, ``angle = 90°``, …) are contextual
provenance recorded on the Evidence/Artifact by the write path; this instrument reads concrete
coordinates and does not consume symbol assumptions.
"""

from typing import Any

from pydantic import BaseModel, Field, StrictFloat, StrictInt, StrictStr, model_validator
from sympy import Float, Integer, acos, pi, simplify
from sympy.geometry import Point

from app.models.enums import ResultStatus
from app.toolbench.adapter import InstrumentResult
from app.toolbench.instruments._sympy_support import ENGINE, ENGINE_VERSION, parse

# A coordinate: an exact int, an exact string ("1/2", "sqrt(2)"), or a float (inexact — see _coord).
CoordScalar = StrictInt | StrictFloat | StrictStr

# Bound each collection so one request cannot fan out into an unbounded number of exact-CAS
# measurements (each angle runs several `simplify`s). The other instruments cap their inputs
# (expression length, oeis term count); this is geometry's equivalent. Generous for any real
# coordinate figure, cheap against a member submitting thousands of measurements as a CPU sink.
_MAX_POINTS = 100
_MAX_MEASUREMENTS = 200  # distances and angles, each


class CoordinateMeasureInput(BaseModel):
    points: dict[str, list[CoordScalar]] = Field(
        description="Named points → coordinate lists, e.g. {'A': [0, 0], 'B': [3, 0], 'C': [3, 4]}."
    )
    distances: list[list[str]] = Field(
        default_factory=list,
        description="Point-name pairs to measure the distance between, e.g. [['A', 'C']].",
    )
    angles: list[list[str]] = Field(
        default_factory=list,
        description="Point-name triples [P, vertex, Q]; the angle is measured at 'vertex', "
        "e.g. [['A', 'B', 'C']] measures the angle at B.",
    )

    @model_validator(mode="after")
    def _check(self) -> "CoordinateMeasureInput":
        if not self.points:
            raise ValueError("at least one point is required")
        if len(self.points) > _MAX_POINTS:
            raise ValueError(f"too many points (max {_MAX_POINTS})")
        if len(self.distances) > _MAX_MEASUREMENTS or len(self.angles) > _MAX_MEASUREMENTS:
            raise ValueError(
                f"too many measurements (max {_MAX_MEASUREMENTS} distances and {_MAX_MEASUREMENTS} "
                "angles)"
            )
        for name, coords in self.points.items():
            if len(coords) not in (2, 3):
                raise ValueError(f"point {name!r} must have 2 or 3 coordinates")
        if len({len(coords) for coords in self.points.values()}) > 1:
            # SymPy silently pads a 2-D point to 3-D (with a warning); reject the mix instead, so a
            # measurement is never taken across dimensions the caller did not intend.
            raise ValueError("all points must share the same dimension (no mixing 2-D and 3-D)")
        if not self.distances and not self.angles:
            raise ValueError("request at least one distance or angle to measure")
        for pair in self.distances:
            if len(pair) != 2:
                raise ValueError(f"a distance must be a pair of point names, got {pair!r}")
            self._require_points(pair)
        for triple in self.angles:
            if len(triple) != 3:
                raise ValueError(f"an angle must be a triple [P, vertex, Q], got {triple!r}")
            self._require_points(triple)
        return self

    def _require_points(self, names: list[str]) -> None:
        missing = [n for n in names if n not in self.points]
        if missing:
            raise ValueError(f"unknown point name(s): {missing}")


class AngleMeasure(BaseModel):
    radians: str  # exact, e.g. "pi/2"
    degrees: str  # exact, e.g. "90"


class CoordinateMeasureOutput(BaseModel):
    distances: dict[str, str]  # "A-C" → "5"
    angles: dict[str, AngleMeasure]  # "A-B-C" → {radians: "pi/2", degrees: "90"}


def _coord(value: CoordScalar) -> Any:
    """Turn one input coordinate into an exact SymPy value (a float stays an inexact ``Float``)."""
    if isinstance(value, bool):  # bool is an int subclass — reject it explicitly
        raise ValueError("a coordinate may not be a boolean")
    if isinstance(value, int):
        return Integer(value)
    if isinstance(value, float):
        return Float(value)
    return parse(value, {})  # string → exact via the safe parser ("1/2", "sqrt(2)")


class CoordinateMeasure:
    """Exact distances and angles between named coordinate points (see module docstring)."""

    name = "geometry.coordinate_measure"
    namespace = "geometry"
    version = "0.1.0"
    engine = ENGINE
    engine_version = ENGINE_VERSION
    description = (
        "Measure exact distances and angles between named coordinate points — e.g. dist(A,C)=5 and "
        "angle(A,B,C)=90° for A=[0,0], B=[3,0], C=[3,4]."
    )
    InputModel = CoordinateMeasureInput
    OutputModel = CoordinateMeasureOutput

    def run(self, inputs: CoordinateMeasureInput, assumptions: dict[str, Any]) -> InstrumentResult:
        points = {
            name: Point(*[_coord(c) for c in coords])
            for name, coords in inputs.points.items()
        }

        distances = {
            f"{p}-{q}": str(points[p].distance(points[q])) for p, q in inputs.distances
        }

        angles: dict[str, AngleMeasure] = {}
        for start, vertex, end in inputs.angles:
            leg_a = points[start] - points[vertex]  # vector from the vertex to each endpoint
            leg_b = points[end] - points[vertex]
            len_a = points[start].distance(points[vertex])
            len_b = points[end].distance(points[vertex])
            if len_a.is_zero or len_b.is_zero:
                # The vertex coincides with an endpoint → a zero-length leg, so the angle is
                # undefined. Refuse (→ 422, mints nothing) rather than divide by zero and record a
                # ``nan`` "measurement" the append-only ledger could never edit out.
                raise ValueError(
                    f"angle {start}-{vertex}-{end} is undefined: the vertex coincides with an "
                    f"endpoint (zero-length leg)"
                )
            cosine = simplify(leg_a.dot(leg_b) / (len_a * len_b))
            radians = simplify(acos(cosine))
            degrees = simplify(radians * 180 / pi)
            angles[f"{start}-{vertex}-{end}"] = AngleMeasure(
                radians=str(radians), degrees=str(degrees)
            )

        output = CoordinateMeasureOutput(distances=distances, angles=angles)
        return InstrumentResult(
            output=output.model_dump(mode="json"),
            status=ResultStatus.RESULT,
            artifact_kind="measurement",
        )


COORDINATE_MEASURE = CoordinateMeasure()
