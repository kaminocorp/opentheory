"""The evidence grade ladder — how strongly a recorded run backs what it was pointed at (0.16.0).

Co-located with the registry **on purpose** (plan D4): adding an instrument must *force* a grading
decision. A registered instrument with no matrix entry fails the conformance harness
(``check_conformance(..., require_grading=True)``) rather than silently reading Grade D.

This module is **pure**: no DB, no session, no imports from ``app.services``. It answers exactly one
question — *given that instrument X returned status S, how rigorous is that?* — and owns the
ladder's
ordering. Traversing the claim → evidence chain and aggregating is the read model's job
(``app/services/grounding.py``).

The grade is a function of **``(instrument, status)``**, not of the instrument alone. That is the
subtlety that makes the ladder honest: ``counterexample.search`` returning ``refuted`` produced an
*exact witness* and settles a universal negatively (**B**), while the same instrument returning
``result`` is finite sampling that settles nothing (**C**). The 0.9.6 / 0.9.9 honesty work made
those
status distinctions rigorous; this table consumes them at the same resolution instead of flattening
them.

**The three honesty rules (verbatim from the plan §3), which the tests assert as such:**

1. **``undecided`` never contributes a grade.** It is not a weak pass; it is the escalation seam.
   Carrying it as "some grade" would be exactly the dishonesty the toolbench contract forbids.
2. **Grade D is the absence of a tool, not a failure.** A human-created ``Evidence`` row (no
   ``instrument`` key in its metadata) is legitimately D — the baseline the bench exists to climb
   out of. It must never render as an error.
3. **A tolerance-only result may never be reported as exact.** No current instrument produces one
   (all six are exact or retrieval), but the ladder must not acquire a "float → B" rule when SciPy
   lands. A numeric instrument whose output is a tolerance-bounded float belongs **below** the exact
   rung, or on its own axis — never at B.

When in doubt, grade **lower** (plan R1): understating rigor is recoverable, overstating it is the
failure mode a provenance ledger exists to prevent.
"""

from app.models.enums import EvidenceGrade, ResultStatus

# --- the matrix (plan §3) -------------------------------------------------------------------------

# Every production instrument declares a grade for **all three** statuses; ``None`` is an explicit
# "no grade from this outcome", never an omission. The conformance harness rejects a registered
# instrument that is missing the instrument key or any of the three status cells (D4), so a new
# instrument cannot enter the catalog without its author making this call deliberately.
#
# ``None`` appears for two distinct reasons, both deliberate:
#   - ``undecided`` everywhere — honesty rule 1.
#   - ``oeis.search`` everywhere — retrieval is **off-ladder** (plan D7). It is graded by source
#     authority and pin quality, not by computation, so it reads ``cited``. The read model maps that
#     via ``Evidence.source_type``, keeping the off-ladder rule in exactly one place.
#   - ``geometry.coordinate_measure`` on ``refuted`` — n/a: the instrument measures, it never
#     refutes. Recorded explicitly so the cell is a decision rather than a gap.
_MATRIX: dict[str, dict[ResultStatus, EvidenceGrade | None]] = {
    # Machine-checked. ``result`` is a Z3 ``unsat`` on ``H ∧ ¬goal`` *after* the vacuous-hypotheses
    # guard (0.13.x), i.e. a real proof; ``refuted`` is a concrete counter-model, i.e. a disproof.
    # Both are the strongest thing the platform can say.
    "z3.prove": {
        ResultStatus.RESULT: EvidenceGrade.A,
        ResultStatus.REFUTED: EvidenceGrade.A,
        ResultStatus.UNDECIDED: None,
    },
    # Exact symbolic equivalence, and (0.9.6) a refutation only on a *provably* non-zero
    # difference —
    # a true identity SymPy cannot close reads ``undecided``, so ``refuted`` here is exact.
    "expr.compare": {
        ResultStatus.RESULT: EvidenceGrade.B,
        ResultStatus.REFUTED: EvidenceGrade.B,
        ResultStatus.UNDECIDED: None,
    },
    # Exact evaluation / relation check; a false relation lands an exact ``counterexample``
    # artifact.
    "calc.eval": {
        ResultStatus.RESULT: EvidenceGrade.B,
        ResultStatus.REFUTED: EvidenceGrade.B,
        ResultStatus.UNDECIDED: None,
    },
    # Exact coordinate measurement (the flagship ``dist(A,C)=5`` / ``angle(A,B,C)=90°``), never a
    # float. It measures; it has no refutation path — hence the explicit n/a.
    "geometry.coordinate_measure": {
        ResultStatus.RESULT: EvidenceGrade.B,
        ResultStatus.REFUTED: None,  # n/a — this instrument never refutes
        ResultStatus.UNDECIDED: None,
    },
    # The asymmetric row, and the reason the matrix is keyed on (instrument, status): a definitive
    # exact witness settles the universal negatively (**B**), while "I swept a finite integer grid
    # and found nothing" is weak support that settles nothing (**C**).
    "counterexample.search": {
        ResultStatus.RESULT: EvidenceGrade.C,
        ResultStatus.REFUTED: EvidenceGrade.B,
        ResultStatus.UNDECIDED: None,
    },
    # Retrieval — off-ladder in every cell (D7). A pin is a citation, not a computation.
    "oeis.search": {
        ResultStatus.RESULT: None,
        ResultStatus.REFUTED: None,
        ResultStatus.UNDECIDED: None,
    },
}

# Ladder ordering for "strongest". ``EvidenceGrade`` is a StrEnum, so a naive ``max()`` would sort
# lexicographically ("A" < "B") and pick the *weakest* grade — precisely the wrong direction for a
# rigor ladder. Ranked explicitly so the ordering is a stated decision, not a side effect of ASCII.
_RANK: dict[EvidenceGrade, int] = {
    EvidenceGrade.A: 4,
    EvidenceGrade.B: 3,
    EvidenceGrade.C: 2,
    EvidenceGrade.D: 1,
}


def grade_for(instrument: str, status: ResultStatus) -> EvidenceGrade | None:
    """The rigor grade a run of ``instrument`` returning ``status`` earns — ``None`` for no grade.

    ``None`` means *"this outcome contributes nothing to the ladder"*, which covers three cases and
    is deliberately **not** the same as Grade D (which asserts "a human said so"):

    - every ``undecided`` (honesty rule 1),
    - every retrieval outcome (off-ladder, D7 — the read model maps it to ``cited``),
    - an unknown instrument or an n/a cell (fail *quiet and low*, per R1).

    An unknown instrument cannot reach production — the conformance harness rejects a registered
    instrument with no matrix entry (D4) — so the fallback exists only so a stale row in the ledger
    (an instrument since renamed or retired) degrades to "ungraded" rather than raising on a read.
    """
    return _MATRIX.get(instrument, {}).get(status)


def strongest(grades: list[EvidenceGrade]) -> EvidenceGrade | None:
    """The highest rung among ``grades`` (``A > B > C > D``); ``None`` for an empty list."""
    if not grades:
        return None
    return max(grades, key=lambda grade: _RANK[grade])


def grading_problems(instrument_name: str) -> list[str]:
    """Ways ``instrument_name`` violates the grading contract (empty list ⇒ graded).

    Shaped like ``conformance.check_conformance`` (a list of human-readable problems, not an
    exception) so the harness can fold these into its own report. Requires **all three** statuses to
    be present: a partially-graded instrument is an author who stopped thinking halfway, and the
    missing cell would silently read "no grade".
    """
    row = _MATRIX.get(instrument_name)
    if row is None:
        return [
            f"{instrument_name!r} has no entry in the grade matrix "
            "(app/toolbench/grading.py) — every registered instrument must declare one"
        ]
    missing = [status.value for status in ResultStatus if status not in row]
    if missing:
        return [
            f"{instrument_name!r} is missing a grade decision for status(es) "
            f"{sorted(missing)} in the grade matrix (app/toolbench/grading.py); "
            "declare an explicit None if the outcome earns no grade"
        ]
    return []
