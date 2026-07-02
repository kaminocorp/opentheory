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
from app.toolbench.instruments import (
    CALC_EVAL,
    COORDINATE_MEASURE,
    COUNTEREXAMPLE_SEARCH,
    EXPR_COMPARE,
)
from app.toolbench.instruments._sympy_support import ENGINE_VERSION, to_latex

ALL_INSTRUMENTS = (CALC_EVAL, COUNTEREXAMPLE_SEARCH, EXPR_COMPARE, COORDINATE_MEASURE)


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
    assert result.output["expression"] == "3**2 + 4**2 == 5**2"
    assert result.output["is_relation"] is True
    assert result.output["value"] is None
    assert result.output["holds"] is True


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
    assert result.output["equivalent"] is True
    assert result.output["difference"] == "0"
    # a classic identity too
    assert _run(EXPR_COMPARE, {"left": "sin(x)**2 + cos(x)**2", "right": "1"}).output[
        "equivalent"
    ] is True


def test_expr_compare_not_equivalent_is_refuted_with_a_witness() -> None:
    result = _run(EXPR_COMPARE, {"left": "x + 1", "right": "x"})
    assert result.status is ResultStatus.REFUTED
    assert result.artifact_kind == "counterexample"
    assert result.output["equivalent"] is False
    assert result.output["difference"] == "1"


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
    angle = result.output["angles"]["A-B-C"]
    assert angle["radians"] == "pi/2"
    assert angle["degrees"] == "90"


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


def test_geometry_bounds_its_input_collections() -> None:
    # 0.9.8: cap points and measurements so one request cannot fan out into an unbounded number of
    # exact-CAS `simplify`s (the other instruments cap their inputs; this is geometry's equivalent).
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="too many points"):
        COORDINATE_MEASURE.InputModel.model_validate(
            {
                "points": {f"P{i}": [i, 0] for i in range(101)},
                "distances": [["P0", "P1"]],
            }
        )
    with pytest.raises(ValidationError, match="too many measurements"):
        COORDINATE_MEASURE.InputModel.model_validate(
            {"points": {"A": [0, 0], "B": [3, 4]}, "distances": [["A", "B"]] * 201}
        )


# --- counterexample.search -----------------------------------------------------------------------


_FLAGSHIP_FALSIFICATION = {
    "relation": "d == a + b",
    "variables": {
        "a": {"min": 1, "max": 10},
        "b": {"min": 1, "max": 10},
        "d": {"min": 1, "max": 15},
    },
}


def test_counterexample_search_conforms() -> None:
    assert check_conformance(COUNTEREXAMPLE_SEARCH, example_inputs=_FLAGSHIP_FALSIFICATION) == []


def test_counterexample_search_finds_a_definitive_witness_for_d_equals_a_plus_b() -> None:
    # Deterministic (a,b,d) order finds the first falsifying assignment — (1,1,1) → 1 == 2, not
    # necessarily the geometry-story triple (3,4,5) → 5 == 7, which appears later in the grid.
    result = _run(COUNTEREXAMPLE_SEARCH, _FLAGSHIP_FALSIFICATION)
    assert result.status is ResultStatus.REFUTED
    assert result.artifact_kind == "counterexample"
    assert result.output["found"] is True
    assert result.output["witness_relation"] == "1 == 2"
    assert result.output["witness"] == {"a": "1", "b": "1", "d": "1"}
    assert result.output["search_space"] == {"a": "1..10", "b": "1..10", "d": "1..15"}
    assert result.output["samples_tried"] == 1


def test_counterexample_search_finds_the_geometry_story_witness_in_isolation() -> None:
    # Pin the search space so the narrative (3,4,5) → 5 == 7 is the first assignment tried.
    result = _run(
        COUNTEREXAMPLE_SEARCH,
        {
            "relation": "d == a + b",
            "variables": {
                "a": {"min": 3, "max": 3},
                "b": {"min": 4, "max": 4},
                "d": {"min": 5, "max": 5},
            },
        },
    )
    assert result.status is ResultStatus.REFUTED
    assert result.output["witness"] == {"a": "3", "b": "4", "d": "5"}
    assert result.output["witness_relation"] == "5 == 7"


def test_counterexample_search_no_witness_is_weak_support_not_proof() -> None:
    result = _run(
        COUNTEREXAMPLE_SEARCH,
        {
            "relation": "a + b == b + a",
            "variables": {"a": {"min": 1, "max": 3}, "b": {"min": 1, "max": 3}},
        },
    )
    assert result.status is ResultStatus.RESULT
    assert result.artifact_kind == "derivation"
    assert result.output["found"] is False
    assert result.output["samples_tried"] == 9


def test_counterexample_search_honours_max_samples_truncation() -> None:
    # A tautology stays true across the grid; cap the search before the space is exhausted.
    result = _run(
        COUNTEREXAMPLE_SEARCH,
        {
            "relation": "a + b == b + a",
            "variables": {
                "a": {"min": 1, "max": 10},
                "b": {"min": 1, "max": 10},
            },
            "max_samples": 5,
        },
    )
    assert result.status is ResultStatus.RESULT
    assert result.output["found"] is False
    assert result.output["samples_tried"] == 5
    assert result.output["truncated"] is True


def test_counterexample_search_rejects_unused_variables() -> None:
    with pytest.raises(ValueError, match="not used in relation"):
        _run(
            COUNTEREXAMPLE_SEARCH,
            {
                "relation": "a + b == b + a",
                "variables": {
                    "a": {"min": 1, "max": 2},
                    "b": {"min": 1, "max": 2},
                    "z": {"min": 1, "max": 2},
                },
            },
        )


def test_counterexample_search_rejects_a_plain_expression() -> None:
    with pytest.raises(ValueError, match="relational operator"):
        _run(
            COUNTEREXAMPLE_SEARCH,
            {
                "relation": "a + b",
                "variables": {"a": {"min": 1, "max": 2}, "b": {"min": 1, "max": 2}},
            },
        )


def test_counterexample_search_rejects_an_oversized_grid() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="search space too large"):
        COUNTEREXAMPLE_SEARCH.InputModel.model_validate(
            {
                "relation": "a + b + c == d",
                "variables": {
                    "a": {"min": 1, "max": 17},
                    "b": {"min": 1, "max": 17},
                    "c": {"min": 1, "max": 17},
                    "d": {"min": 1, "max": 17},
                },
            }
        )


def test_counterexample_search_rejects_assumptions() -> None:
    with pytest.raises(ValueError, match="does not accept assumptions"):
        COUNTEREXAMPLE_SEARCH.run(
            COUNTEREXAMPLE_SEARCH.InputModel.model_validate(_FLAGSHIP_FALSIFICATION),
            {"x": {"positive": True}},
        )


def test_counterexample_search_blocks_injection_in_the_relation() -> None:
    with pytest.raises(ValueError):
        _run(
            COUNTEREXAMPLE_SEARCH,
            {
                "relation": "a == __import__('os').getpid()",
                "variables": {"a": {"min": 1, "max": 2}},
            },
        )


# --- safety boundary ------------------------------------------------------------------------------


def test_parse_namespace_blocks_the_obvious_injection() -> None:
    # A bare ``__import__`` reaching anything: the instrument fails to run (→ 422).
    with pytest.raises(ValueError):
        _run(CALC_EVAL, {"expression": "__import__('os').getcwd()"})


@pytest.mark.parametrize(
    "payload",
    [
        # The eval-escape vectors (all confirmed to execute against the un-gated parse_expr): the
        # AST allow-list must reject every one *before* parse_expr's eval sees it.
        "sqrt.__globals__['__builtins__']['__import__']('os').getpid()",  # builtins via __globals__
        "(1).__class__.__mro__[-1].__subclasses__()",  # attribute walk to object.__subclasses__
        "().__class__",  # attribute access on a literal
        "sqrt.__doc__[0]",  # subscripting
        "__import__('os')",  # a bare dunder name
    ],
    ids=["globals-walk", "class-walk", "attr-on-literal", "subscript", "dunder-name"],
)
def test_parse_blocks_the_eval_escape(payload: str) -> None:
    # The load-bearing security invariant: no input can reach attribute access, subscripting, or a
    # dunder name — the only routes to arbitrary code execution through parse_expr's eval.
    with pytest.raises(ValueError):
        _run(CALC_EVAL, {"expression": payload})


@pytest.mark.parametrize(
    "payload",
    [
        "2**100000",  # a single huge constant exponent — the cheapest compute bomb
        "9" * 1001,  # over the raw-length cap
    ],
    ids=["huge-exponent", "too-long"],
)
def test_parse_rejects_cheap_resource_bombs(payload: str) -> None:
    with pytest.raises(ValueError):
        _run(CALC_EVAL, {"expression": payload})


@pytest.mark.parametrize(
    "payload",
    [
        "2**(2**30)",  # right-nested numeric power — exponent evaluates to ~10^9
        "2^(2^30)",  # same via '^' (convert_xor) — must be caught after xor-folding too
        "2**(1 + 2**40)",  # the power is buried inside the exponent, still numeric-only
    ],
    ids=["tower", "tower-caret", "tower-buried"],
)
def test_parse_rejects_a_numeric_power_tower(payload: str) -> None:
    # 0.9.8: the constant-exponent cap never sees a power tower (the exponent is a BinOp, not a
    # literal), yet 2**(2**30) OOMs the worker. The AST gate must reject a *numeric* power exponent.
    with pytest.raises(ValueError):
        _run(CALC_EVAL, {"expression": payload})


def test_parse_allows_a_symbolic_power_tower_and_plain_numeric_exponents() -> None:
    # The discriminator is a *name* in the exponent: a symbolic exponent stays symbolic in SymPy (no
    # giant int), so it must not be rejected; a numeric exponent that is not itself a power is fine.
    assert _run(CALC_EVAL, {"expression": "2**(2**n)"}).status is ResultStatus.RESULT
    assert _run(CALC_EVAL, {"expression": "2**(2*10)"}).output["value"] == "1048576"


def test_parse_still_allows_legitimate_math() -> None:
    # The gate must not regress real inputs: functions, symbols, powers, '^'-as-exponent, rationals.
    result = _run(CALC_EVAL, {"expression": "sqrt(2) + sin(x)**2 + 1/3"})
    assert result.status is ResultStatus.RESULT
    assert _run(CALC_EVAL, {"expression": "3^2 + 4^2"}).output["value"] == "25"


# --- LaTeX companions (0.10.4) -------------------------------------------------------------------


def test_to_latex_renders_superscripts() -> None:
    latex = to_latex("x**2 - 1")
    assert latex is not None
    assert "^{" in latex  # superscript markup, not raw "**"


def test_calc_eval_emits_expression_and_value_latex() -> None:
    result = _run(CALC_EVAL, {"expression": "x**2 - 1"})
    assert result.output["expression_latex"] is not None
    assert "^{" in result.output["expression_latex"]
    assert result.output["value_latex"] is not None


def test_expr_compare_emits_latex_companions() -> None:
    result = _run(EXPR_COMPARE, {"left": "x**2", "right": "x"})
    assert result.output["left_latex"] is not None
    assert result.output["right_latex"] is not None
    assert result.output["difference_latex"] is not None


def test_geometry_emits_latex_companions() -> None:
    result = _run(COORDINATE_MEASURE, _CORNER)
    assert result.output["distances_latex"]["A-C"] == "5"
    angle = result.output["angles"]["A-B-C"]
    assert angle["radians_latex"] is not None
    assert angle["degrees_latex"] == "90"


def test_counterexample_search_emits_relation_latex() -> None:
    result = _run(
        COUNTEREXAMPLE_SEARCH,
        {
            "relation": "d == a + b",
            "variables": {
                "a": {"min": 3, "max": 3},
                "b": {"min": 4, "max": 4},
                "d": {"min": 5, "max": 5},
            },
        },
    )
    assert result.output["relation_latex"] is not None
    assert result.output["witness_relation_latex"] is not None
    assert "5" in result.output["witness_relation_latex"]
    assert "7" in result.output["witness_relation_latex"]


def test_every_run_output_validates_against_its_output_model() -> None:
    # The write path hashes ``output``; the conformance harness also re-checks it, but assert here
    # that each instrument's live output round-trips through its declared OutputModel.
    cases = [
        (CALC_EVAL, {"expression": "2 + 2"}),
        (COUNTEREXAMPLE_SEARCH, _FLAGSHIP_FALSIFICATION),
        (EXPR_COMPARE, {"left": "x", "right": "x"}),
        (COORDINATE_MEASURE, _CORNER),
    ]
    for instrument, inputs in cases:
        result = _run(instrument, inputs)
        assert isinstance(result, InstrumentResult)
        instrument.OutputModel.model_validate(result.output)  # raises if it does not conform
