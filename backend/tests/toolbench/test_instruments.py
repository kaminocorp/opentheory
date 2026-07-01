"""Phase 4 — the Tier-0 SymPy instruments (calc.eval, expr.compare, geometry.coordinate_measure).

Pure in-process (no DB). Each instrument gets its Phase-2 conformance check *and* real behavioural
assertions — the three honest outcomes, the exact (never float) values, the assumptions plumbing,
and the parse-namespace safety boundary. The ledger side is covered separately (DB-backed) in
``test_instruments_write_path.py``.

See ``docs/executing/toolbench-provenance-and-first-instruments.md`` Phase 4.
"""

from typing import Any

import pytest

from app.models.enums import ResultStatus
from app.toolbench.adapter import InstrumentResult
from app.toolbench.conformance import check_conformance
from app.toolbench.instruments import CALC_EVAL, COORDINATE_MEASURE, EXPR_COMPARE
from app.toolbench.instruments._sympy_support import ENGINE_VERSION

ALL_INSTRUMENTS = (CALC_EVAL, EXPR_COMPARE, COORDINATE_MEASURE)


def _run(instrument: Any, inputs: dict[str, Any], assumptions: dict[str, Any] | None = None):
    """Run an instrument the way the write path does: validate inputs, then ``run``."""
    validated = instrument.InputModel.model_validate(inputs)
    return instrument.run(validated, assumptions or {})


# --- shared contract -----------------------------------------------------------------------------


@pytest.mark.parametrize("instrument", ALL_INSTRUMENTS, ids=lambda i: i.name)
def test_engine_is_pinned_to_the_installed_sympy(instrument: Any) -> None:
    # The blame tuple's reproducibility hinges on the recorded engine version being the real one.
    assert instrument.engine == "sympy"
    assert instrument.engine_version == ENGINE_VERSION
    assert instrument.version == "0.1.0"


# --- calc.eval -----------------------------------------------------------------------------------


def test_calc_eval_conforms() -> None:
    assert check_conformance(CALC_EVAL, example_inputs={"expression": "2 + 2"}) == []


def test_calc_eval_evaluates_values_exactly() -> None:
    assert _run(CALC_EVAL, {"expression": "2 + 2"}).output["value"] == "4"
    assert _run(CALC_EVAL, {"expression": "3**2 + 4**2"}).output["value"] == "25"
    # exact rational — no rounding
    assert _run(CALC_EVAL, {"expression": "1/3 + 1/6"}).output["value"] == "1/2"
    # exact surd — never a float (a float is not an exact content hash)
    assert _run(CALC_EVAL, {"expression": "sqrt(2)"}).output["value"] == "sqrt(2)"
    # '^' reads as exponentiation
    assert _run(CALC_EVAL, {"expression": "3^2 + 4^2"}).output["value"] == "25"


def test_calc_eval_true_relation_is_result() -> None:
    result = _run(CALC_EVAL, {"expression": "3**2 + 4**2 == 5**2"})
    assert result.status is ResultStatus.RESULT
    assert result.artifact_kind == "derivation"
    assert result.output == {
        "expression": "3**2 + 4**2 == 5**2",
        "is_relation": True,
        "value": None,
        "holds": True,
    }


def test_calc_eval_false_relation_is_a_refuted_counterexample() -> None:
    result = _run(CALC_EVAL, {"expression": "5 == 7"})
    assert result.status is ResultStatus.REFUTED  # the falsification engine
    assert result.artifact_kind == "counterexample"
    assert result.output["holds"] is False


def test_calc_eval_inequalities() -> None:
    assert _run(CALC_EVAL, {"expression": "sqrt(2) < 2"}).status is ResultStatus.RESULT
    assert _run(CALC_EVAL, {"expression": "1/2 >= 1"}).status is ResultStatus.REFUTED


def test_calc_eval_undecidable_relation_is_undecided() -> None:
    # A relation still carrying a free symbol cannot be settled → undecided, never a silent pass.
    result = _run(CALC_EVAL, {"expression": "x**2 == 2*x"})
    assert result.status is ResultStatus.UNDECIDED
    assert result.output["holds"] is None


def test_calc_eval_lone_equals_is_rejected() -> None:
    with pytest.raises(ValueError, match="=="):
        _run(CALC_EVAL, {"expression": "x = 2"})


# --- expr.compare ---------------------------------------------------------------------------------


def test_expr_compare_conforms() -> None:
    assert (
        check_conformance(EXPR_COMPARE, example_inputs={"left": "x", "right": "x"}) == []
    )


def test_expr_compare_equivalent_is_result() -> None:
    result = _run(EXPR_COMPARE, {"left": "(a + b)**2 - 2*a*b", "right": "a**2 + b**2"})
    assert result.status is ResultStatus.RESULT
    assert result.output == {"equivalent": True, "difference": "0"}
    # a classic identity too
    assert _run(EXPR_COMPARE, {"left": "sin(x)**2 + cos(x)**2", "right": "1"}).output[
        "equivalent"
    ] is True


def test_expr_compare_not_equivalent_is_refuted_with_a_witness() -> None:
    result = _run(EXPR_COMPARE, {"left": "x + 1", "right": "x"})
    assert result.status is ResultStatus.REFUTED
    assert result.artifact_kind == "counterexample"
    assert result.output == {"equivalent": False, "difference": "1"}


def test_expr_compare_unknown_is_undecided() -> None:
    result = _run(EXPR_COMPARE, {"left": "sqrt(x**2)", "right": "x"})
    assert result.status is ResultStatus.UNDECIDED
    assert result.output["equivalent"] is None


def test_expr_compare_assumptions_change_the_outcome() -> None:
    # √(x²) = x is only equivalent under x > 0 — the assumptions plumbing must reach the symbol.
    inputs = {"left": "sqrt(x**2)", "right": "x"}
    assert _run(EXPR_COMPARE, inputs).status is ResultStatus.UNDECIDED
    under_positive = _run(EXPR_COMPARE, inputs, {"x": {"positive": True}})
    assert under_positive.status is ResultStatus.RESULT
    assert under_positive.output["equivalent"] is True


def test_expr_compare_rejects_an_unknown_assumption_predicate() -> None:
    # A misspelled predicate must fail loud — silently ignoring it would record a misleading result.
    with pytest.raises(ValueError, match="unknown SymPy assumption"):
        _run(EXPR_COMPARE, {"left": "x", "right": "x"}, {"x": {"postive": True}})


def test_expr_compare_true_identity_sympy_cannot_close_is_undecided_not_refuted() -> None:
    # Regression: a genuinely TRUE identity that simplify cannot reduce to 0 must be UNDECIDED, not
    # a false REFUTED "counterexample". cos(π/7) − cos(2π/7) + cos(3π/7) = 1/2 is exactly true, but
    # simplify leaves a symbol-free residue whose is_zero is None. Keying the refuted branch off
    # `is_number` (rather than `is_zero is False`) rendered this true claim as a definitive
    # counterexample — the one error a provenance ledger must never make.
    result = _run(
        EXPR_COMPARE, {"left": "cos(pi/7) - cos(2*pi/7) + cos(3*pi/7)", "right": "1/2"}
    )
    assert result.status is ResultStatus.UNDECIDED
    assert result.output["equivalent"] is None


def test_expr_compare_provably_nonzero_still_refutes() -> None:
    # The fix must not weaken genuine refutations: a concrete non-zero difference, and a symbolic
    # difference SymPy can *prove* is never zero (Abs(x) + 1 ≥ 1), both stay REFUTED.
    assert _run(EXPR_COMPARE, {"left": "2", "right": "3"}).status is ResultStatus.REFUTED
    symbolic = _run(EXPR_COMPARE, {"left": "Abs(x) + 1", "right": "0"})
    assert symbolic.status is ResultStatus.REFUTED
    assert symbolic.output["equivalent"] is False


# --- geometry.coordinate_measure ------------------------------------------------------------------

_CORNER = {
    "points": {"A": [0, 0], "B": [3, 0], "C": [3, 4]},
    "distances": [["A", "C"]],
    "angles": [["A", "B", "C"]],
}


def test_geometry_conforms() -> None:
    assert check_conformance(COORDINATE_MEASURE, example_inputs=_CORNER) == []


def test_geometry_measures_the_corner_exactly() -> None:
    result = _run(COORDINATE_MEASURE, _CORNER)
    assert result.status is ResultStatus.RESULT
    assert result.artifact_kind == "measurement"
    assert result.output["distances"] == {"A-C": "5"}  # exact 3-4-5
    assert result.output["angles"] == {"A-B-C": {"radians": "pi/2", "degrees": "90"}}


def test_geometry_supports_exact_string_and_3d_coordinates() -> None:
    result = _run(
        COORDINATE_MEASURE,
        {"points": {"O": [0, 0, 0], "P": ["1/2", 0, 0]}, "distances": [["O", "P"]]},
    )
    assert result.output["distances"] == {"O-P": "1/2"}  # exact, not 0.5


def test_geometry_requires_a_measurement() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        COORDINATE_MEASURE.InputModel.model_validate({"points": {"A": [0, 0]}})


def test_geometry_rejects_an_unknown_point_name() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        COORDINATE_MEASURE.InputModel.model_validate(
            {"points": {"A": [0, 0]}, "distances": [["A", "Z"]]}
        )


def test_geometry_rejects_a_degenerate_angle() -> None:
    # Regression: a zero-length leg (vertex coincident with an endpoint) makes the angle undefined.
    # The instrument must refuse (→ 422, mints nothing) rather than record a nan "measurement".
    with pytest.raises(ValueError, match="undefined"):
        _run(
            COORDINATE_MEASURE,
            {"points": {"A": [0, 0], "C": [3, 4]}, "angles": [["A", "A", "C"]]},
        )


def test_geometry_rejects_mixed_dimension_points() -> None:
    # Regression: SymPy silently pads a 2-D point to 3-D; reject the mix so a measurement is never
    # taken across dimensions the caller did not intend.
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        COORDINATE_MEASURE.InputModel.model_validate(
            {"points": {"A": [0, 0], "B": [3, 0, 4]}, "distances": [["A", "B"]]}
        )


# --- safety boundary ------------------------------------------------------------------------------


def test_parse_namespace_blocks_the_obvious_injection() -> None:
    # Not a real sandbox (that is the deferred execution substrate) — but the curated namespace must
    # at least stop a bare ``__import__`` reaching anything: the instrument fails to run (→ 422).
    with pytest.raises(ValueError):
        _run(CALC_EVAL, {"expression": "__import__('os').getcwd()"})


def test_every_run_output_validates_against_its_output_model() -> None:
    # The write path hashes ``output``; the conformance harness also re-checks it, but assert here
    # that each instrument's live output round-trips through its declared OutputModel.
    cases = [
        (CALC_EVAL, {"expression": "2 + 2"}),
        (EXPR_COMPARE, {"left": "x", "right": "x"}),
        (COORDINATE_MEASURE, _CORNER),
    ]
    for instrument, inputs in cases:
        result = _run(instrument, inputs)
        assert isinstance(result, InstrumentResult)
        instrument.OutputModel.model_validate(result.output)  # raises if it does not conform
