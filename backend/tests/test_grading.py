"""Phase 1 — the evidence grade ladder derivation (0.16.0).

Pure, DB-free: the matrix is a function of ``(instrument, status)`` and nothing else, so every cell
of plan §3 is asserted directly. The three honesty rules get their own named tests — this file is
where a wrong *epistemic* call (plan R1) is supposed to be caught, not a wrong line of code.

See ``docs/executing/claim-grounding-0.16.md`` §3 and Phase 1.
"""

import pytest

from app.models.enums import EvidenceGrade, ResultStatus
from app.toolbench.conformance import check_conformance
from app.toolbench.grading import (
    grade_for,
    grading_problems,
    instruments_reaching,
    raise_path,
    strongest,
)
from app.toolbench.registry import registry

# The six production instruments, for the exhaustive sweeps below.
INSTRUMENTS = (
    "z3.prove",
    "expr.compare",
    "calc.eval",
    "geometry.coordinate_measure",
    "counterexample.search",
    "oeis.search",
)

# --- every cell of the §3 matrix ------------------------------------------------------------------

# (instrument, status, expected grade) — transcribed cell by cell from the plan's table so a
# divergence between the doc and the code shows up as a failing assertion, not a silent drift.
MATRIX_CELLS = [
    ("z3.prove", ResultStatus.RESULT, EvidenceGrade.A),
    ("z3.prove", ResultStatus.REFUTED, EvidenceGrade.A),
    ("z3.prove", ResultStatus.UNDECIDED, None),
    ("expr.compare", ResultStatus.RESULT, EvidenceGrade.B),
    ("expr.compare", ResultStatus.REFUTED, EvidenceGrade.B),
    ("expr.compare", ResultStatus.UNDECIDED, None),
    ("calc.eval", ResultStatus.RESULT, EvidenceGrade.B),
    ("calc.eval", ResultStatus.REFUTED, EvidenceGrade.B),
    ("calc.eval", ResultStatus.UNDECIDED, None),
    ("geometry.coordinate_measure", ResultStatus.RESULT, EvidenceGrade.B),
    ("geometry.coordinate_measure", ResultStatus.REFUTED, None),  # n/a — never refutes
    ("geometry.coordinate_measure", ResultStatus.UNDECIDED, None),
    ("counterexample.search", ResultStatus.RESULT, EvidenceGrade.C),
    ("counterexample.search", ResultStatus.REFUTED, EvidenceGrade.B),
    ("counterexample.search", ResultStatus.UNDECIDED, None),
    ("oeis.search", ResultStatus.RESULT, None),  # off-ladder (D7)
    ("oeis.search", ResultStatus.REFUTED, None),
    ("oeis.search", ResultStatus.UNDECIDED, None),
]


@pytest.mark.parametrize(
    ("instrument", "status", "expected"),
    MATRIX_CELLS,
    ids=[f"{i}:{s.value}" for i, s, _ in MATRIX_CELLS],
)
def test_matrix_cell(
    instrument: str, status: ResultStatus, expected: EvidenceGrade | None
) -> None:
    assert grade_for(instrument, status) is expected


# --- honesty rule 1: undecided never contributes a grade ------------------------------------------


@pytest.mark.parametrize("instrument", INSTRUMENTS)
def test_undecided_never_earns_a_grade(instrument: str) -> None:
    """Rule 1 — ``undecided`` is the escalation seam, not a weak pass.

    Asserted for *every* instrument, including the two that can produce a machine-checked A: a Z3
    timeout is an honest "I could not decide", and grading it would be exactly the dishonesty the
    toolbench contract forbids.
    """
    assert grade_for(instrument, ResultStatus.UNDECIDED) is None


# --- the asymmetric row (why the key is a pair, not an instrument) --------------------------------


def test_counterexample_search_refutation_outranks_its_own_weak_support() -> None:
    """An exact witness settles the universal (**B**); a finite grid sweep does not (**C**)."""
    refuted = grade_for("counterexample.search", ResultStatus.REFUTED)
    supported = grade_for("counterexample.search", ResultStatus.RESULT)
    assert refuted is EvidenceGrade.B
    assert supported is EvidenceGrade.C
    assert strongest([refuted, supported]) is EvidenceGrade.B


def test_machine_checked_outranks_exact_outranks_sampled() -> None:
    """The ladder's whole point: A > B > C > D, as an ordering the code actually implements."""
    assert strongest([EvidenceGrade.D, EvidenceGrade.C]) is EvidenceGrade.C
    assert strongest([EvidenceGrade.C, EvidenceGrade.B]) is EvidenceGrade.B
    assert strongest([EvidenceGrade.B, EvidenceGrade.A]) is EvidenceGrade.A
    assert strongest([EvidenceGrade.D, EvidenceGrade.A, EvidenceGrade.C]) is EvidenceGrade.A


def test_strongest_is_not_lexicographic() -> None:
    """Guards ``_RANK``: a naive ``max()`` on a StrEnum returns "D", the *weakest* rung."""
    assert strongest([EvidenceGrade.A, EvidenceGrade.D]) is EvidenceGrade.A
    assert max([EvidenceGrade.A, EvidenceGrade.D]) is EvidenceGrade.D  # what NOT to do


def test_strongest_of_nothing_is_none() -> None:
    assert strongest([]) is None


# --- retrieval is off-ladder (D7) -----------------------------------------------------------------


@pytest.mark.parametrize("status", list(ResultStatus))
def test_retrieval_never_earns_a_letter(status: ResultStatus) -> None:
    """``oeis.search`` is graded by source authority, not computation — it reads ``cited``.

    The letter is withheld here *and* the read model gates ``cited`` on ``Evidence.source_type``;
    both point the same way, so a pin can never be mistaken for a computed result.
    """
    assert grade_for("oeis.search", status) is None


# --- the conservative fallback --------------------------------------------------------------------


def test_unknown_instrument_grades_nothing_rather_than_raising() -> None:
    """A stale ledger row (an instrument since renamed/retired) degrades quietly, never 500s.

    ``None`` here is *not* Grade D: D asserts "a human said so", which would be a false statement
    about a row that was in fact produced by a tool. Understating is recoverable (R1).
    """
    assert grade_for("does.not.exist", ResultStatus.RESULT) is None


# --- D4: the harness forces a grading decision ----------------------------------------------------


def test_every_registered_instrument_is_graded() -> None:
    """D4 — the production registry and the grade matrix agree, instrument for instrument."""
    for instrument in registry.all():
        assert grading_problems(instrument.name) == [], instrument.name


def test_conformance_rejects_a_registered_instrument_with_no_matrix_row() -> None:
    """Comment a row out of ``_MATRIX`` and this is the test that goes red."""
    problems = grading_problems("brand.new")
    assert problems
    assert "grade matrix" in problems[0]


def test_conformance_flags_a_partially_graded_instrument(monkeypatch: pytest.MonkeyPatch) -> None:
    """Declaring two of three statuses is not a decision — the missing cell must fail loudly."""
    from app.toolbench import grading

    monkeypatch.setitem(
        grading._MATRIX,
        "partial.instrument",
        {ResultStatus.RESULT: EvidenceGrade.B},  # REFUTED + UNDECIDED unstated
    )
    problems = grading_problems("partial.instrument")
    assert problems
    assert "refuted" in problems[0] and "undecided" in problems[0]


# --- 0.16.1: reading the matrix backwards (the raise path) ----------------------------------------


def test_only_z3_can_reach_grade_a_today() -> None:
    """Acceptance 1 — the A-path names the one machine-checked instrument, and nothing else.

    This is the assertion that goes red the day Lean lands, which is the point: the prompt's advice
    is derived from the matrix, so widening the matrix widens the advice with no prompt edit.
    """
    assert instruments_reaching(EvidenceGrade.A) == ["z3.prove"]


def test_capability_is_read_across_all_statuses_not_just_result() -> None:
    """``counterexample.search`` is B-capable via ``refuted`` even though its ``result`` cell is C.

    Planning asks what a run *might* produce, not what it usually does — the run might refute.
    """
    assert grade_for("counterexample.search", ResultStatus.RESULT) is EvidenceGrade.C
    assert "counterexample.search" in instruments_reaching(EvidenceGrade.B)


def test_retrieval_is_never_a_way_to_raise_a_rung() -> None:
    """Off-ladder in the matrix ⇒ off-ladder in the advice. A pin is a citation, not a rung."""
    for grade in EvidenceGrade:
        assert "oeis.search" not in instruments_reaching(grade)
    assert "oeis.search" not in raise_path(None)


def test_raise_path_from_b_is_the_a_capable_set() -> None:
    """A claim already at exact-symbolic B has exactly one way up: machine-check it."""
    assert raise_path(EvidenceGrade.B) == ["z3.prove"]


def test_nothing_beats_a_machine_checked_proof() -> None:
    """Acceptance 2's engine — an empty raise path is how the planner learns to stop spending."""
    assert raise_path(EvidenceGrade.A) == []


def test_raise_path_from_nothing_offers_every_graded_instrument() -> None:
    """An ungrounded claim can be improved by any instrument that grades at all."""
    path = raise_path(None)
    assert set(path) == {
        "z3.prove",
        "expr.compare",
        "calc.eval",
        "geometry.coordinate_measure",
        "counterexample.search",
    }


def test_raise_path_is_strictly_stronger_than_the_current_rung() -> None:
    """``raise_path`` excludes the current rung; ``instruments_reaching`` includes it.

    The distinction matters: an instrument that can only match what a claim already has is not a
    way *up*, and offering it would be the activity-without-yield this release exists to prevent.
    """
    assert "counterexample.search" in instruments_reaching(EvidenceGrade.C)
    assert "counterexample.search" in raise_path(EvidenceGrade.C)  # can still reach B
    # geometry tops out at B, so it is a way up from C but not from B.
    assert "geometry.coordinate_measure" in raise_path(EvidenceGrade.C)
    assert "geometry.coordinate_measure" not in raise_path(EvidenceGrade.B)


def test_check_conformance_grading_is_opt_in() -> None:
    """A throwaway fixture stays conformant; only ``require_grading`` demands a matrix row."""

    class Fixture:
        name = "demo.ungraded"
        namespace = "demo"
        version = "0.0.0"
        engine = "builtin"
        engine_version = "1.0"
        description = "A fixture with no grade matrix row."
        InputModel = _Empty = type("_In", (), {})
        OutputModel = _Empty

        def run(self, inputs, assumptions):  # pragma: no cover - never invoked structurally
            raise NotImplementedError

    fixture = Fixture()
    default_problems = check_conformance(fixture)  # type: ignore[arg-type]
    strict_problems = check_conformance(fixture, require_grading=True)  # type: ignore[arg-type]

    assert not any("grade matrix" in p for p in default_problems)
    assert any("grade matrix" in p for p in strict_problems)
