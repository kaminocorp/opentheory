"""Phase 2 — the grounding aggregation and display precedence (0.16.0), DB-free.

``compute_grounding`` is deliberately split out of the batch loader so §3.1 (aggregation) and the
display-precedence table are testable without a database. The DB-gated round-trips through
``run_instrument`` live in ``tests/test_read_models.py``; this file pins the *rules*, which is where
a wrong epistemic call would hide.

Every acceptance criterion from the plan §6 that does not require a live chokepoint is asserted here
by name.

See ``docs/executing/claim-grounding-0.16.md`` §3.1 and Phase 2.
"""

from typing import Any
from uuid import uuid4

from app.models.enums import EvidenceGrade
from app.schemas.claim import ClaimGrounding
from app.services.grounding import compute_grounding, compute_yield

# --- link builders (relation_kind, source_type, evidence_metadata) --------------------------------


def tool_link(
    relation: str, instrument: str, status: str
) -> tuple[str, str, dict[str, Any]]:
    """An evidence row as ``tool_runs.py`` writes it for a *compute* instrument."""
    return (relation, "tool", {"output": {}, "status": status, "instrument": instrument})


def pin_link(
    relation: str, status: str = "result", provider: str = "oeis"
) -> tuple[str, str, dict[str, Any]]:
    """An evidence row as ``tool_runs.py`` writes it for a *retrieval* instrument."""
    return (
        relation,
        provider,
        {"output": {}, "status": status, "instrument": "oeis.search"},
    )


def human_link(relation: str, source_type: str = "paper") -> tuple[str, str, dict[str, Any]]:
    """A hand-attached evidence row: no ``instrument`` key anywhere in its metadata."""
    return (relation, source_type, {})


# --- acceptance 1: a proof reads ``proven`` with zero validations ---------------------------------


def test_z3_proof_reads_proven() -> None:
    grounding = compute_grounding([tool_link("support", "z3.prove", "result")])
    assert grounding.support is EvidenceGrade.A
    assert grounding.counter is None
    assert grounding.headline == "proven"


# --- acceptance 2: an exact counter dominates any amount of support (D8) --------------------------


def test_exact_counterexample_dominates_three_supporting_results() -> None:
    grounding = compute_grounding(
        [
            tool_link("support", "calc.eval", "result"),
            tool_link("support", "expr.compare", "result"),
            tool_link("support", "counterexample.search", "result"),
            tool_link("weaken", "counterexample.search", "refuted"),  # the exact witness
        ]
    )
    assert grounding.support is EvidenceGrade.B  # support is still reported, not erased
    assert grounding.counter is EvidenceGrade.B
    assert grounding.headline == "refuted"


def test_machine_checked_counter_model_also_refutes() -> None:
    grounding = compute_grounding([tool_link("weaken", "z3.prove", "refuted")])
    assert grounding.counter is EvidenceGrade.A
    assert grounding.headline == "refuted"


def test_a_refutation_dominates_even_a_machine_checked_proof() -> None:
    """A contradictory ledger must read as *contested reality*, never quietly as ``proven``."""
    grounding = compute_grounding(
        [
            tool_link("support", "z3.prove", "result"),
            tool_link("weaken", "z3.prove", "refuted"),
        ]
    )
    assert grounding.support is EvidenceGrade.A
    assert grounding.counter is EvidenceGrade.A
    assert grounding.headline == "refuted"


def test_a_weak_counter_does_not_refute() -> None:
    """Only A/B counters dominate. A sampled or human counter *contests*; that is the other axis.

    ``counterexample.search`` returning ``result`` means "I swept a finite grid and found nothing" —
    linked as ``weaken`` it is a C-grade counter, which must not read as a settled refutation.
    """
    grounding = compute_grounding(
        [
            tool_link("support", "calc.eval", "result"),
            tool_link("weaken", "counterexample.search", "result"),  # C, not B
        ]
    )
    assert grounding.counter is EvidenceGrade.C
    assert grounding.headline == "B"  # the supporting rung still leads


def test_a_weak_counter_alone_leaves_the_claim_ungrounded() -> None:
    """No support and only a C/D counter: nothing is settled either way (§3.1 "nothing")."""
    grounding = compute_grounding([human_link("weaken")])
    assert grounding.counter is EvidenceGrade.D
    assert grounding.support is None
    assert grounding.headline == "ungrounded"


# --- acceptance 3: an undecided run changes nothing (honesty rule 1) ------------------------------


def test_undecided_run_leaves_the_claim_ungrounded() -> None:
    """``undecided`` lands a ``context`` link *and* earns no grade — two independent guards."""
    grounding = compute_grounding([tool_link("context", "z3.prove", "undecided")])
    assert grounding == compute_grounding([])
    assert grounding.headline == "ungrounded"


def test_undecided_forced_onto_the_support_side_still_contributes_nothing() -> None:
    """The caller may pin ``relation_kind``, so the ``context`` default is not the only defence.

    Even filed as support, an undecided outcome must not land on the ladder — and specifically must
    not fall through to Grade D, which would falsely assert the row was human-asserted.
    """
    grounding = compute_grounding([tool_link("support", "z3.prove", "undecided")])
    assert grounding.support is None
    assert grounding.headline == "ungrounded"


def test_undecided_does_not_dilute_a_real_result() -> None:
    grounding = compute_grounding(
        [
            tool_link("support", "expr.compare", "result"),
            tool_link("support", "z3.prove", "undecided"),
        ]
    )
    assert grounding.support is EvidenceGrade.B
    assert grounding.headline == "B"


# --- acceptance 4: a hand-created evidence row is D, calmly (honesty rule 2) ----------------------


def test_human_evidence_grades_d() -> None:
    grounding = compute_grounding([human_link("support")])
    assert grounding.support is EvidenceGrade.D
    assert grounding.headline == "D"
    assert grounding.cited is False


def test_a_tool_result_outranks_a_human_assertion() -> None:
    grounding = compute_grounding(
        [human_link("support"), tool_link("support", "calc.eval", "result")]
    )
    assert grounding.support is EvidenceGrade.B
    assert grounding.headline == "B"


def test_hand_attached_paper_is_not_promoted_to_cited() -> None:
    """A human typing ``source_type: "paper"`` is still an assertion, not a machine-made pin.

    ``cited`` is reserved for a retrieval *instrument*'s pin (url + retrieved_at + response hash);
    letting an arbitrary hand-typed ``source_type`` reach it would make the ladder gameable
    from the attach-evidence form.
    """
    grounding = compute_grounding([human_link("support", source_type="paper")])
    assert grounding.cited is False
    assert grounding.support is EvidenceGrade.D


# --- acceptance 5: a retrieval pin reads ``cited``, never a letter (D7) ---------------------------


def test_oeis_pin_reads_cited_and_earns_no_letter() -> None:
    grounding = compute_grounding([pin_link("support")])
    assert grounding.cited is True
    assert grounding.support is None
    assert grounding.counter is None
    assert grounding.headline == "cited"


def test_a_computed_grade_outranks_a_citation_in_the_headline() -> None:
    grounding = compute_grounding(
        [pin_link("support"), tool_link("support", "calc.eval", "result")]
    )
    assert grounding.cited is True  # the pin is still reported
    assert grounding.headline == "B"  # …but the computed rung leads


def test_a_failed_lookup_is_not_a_citation() -> None:
    """An ``oeis.search`` that matched nothing must not raise the claim off ``ungrounded``.

    A deliberate tightening of §3.1's literal wording, implied by honesty rule 1 — see
    ``_is_live_pin``. The pin is still on the ledger; it just does not lift the rung.
    """
    grounding = compute_grounding([pin_link("context", status="undecided")])
    assert grounding.cited is False
    assert grounding.headline == "ungrounded"


# --- the ``context`` relation feeds neither side --------------------------------------------------


def test_context_links_contribute_to_neither_side() -> None:
    grounding = compute_grounding(
        [
            tool_link("context", "z3.prove", "result"),
            tool_link("context", "calc.eval", "refuted"),
        ]
    )
    assert grounding.support is None
    assert grounding.counter is None
    assert grounding.headline == "ungrounded"


# --- defensive: malformed or stale rows degrade quietly, never to a false D -----------------------


def test_unparseable_status_grades_nothing() -> None:
    grounding = compute_grounding([("support", "tool", {"instrument": "calc.eval"})])
    assert grounding.support is None
    assert grounding.headline == "ungrounded"


def test_retired_instrument_grades_nothing() -> None:
    grounding = compute_grounding([tool_link("support", "since.retired", "result")])
    assert grounding.support is None
    assert grounding.headline == "ungrounded"


def test_no_links_at_all_is_ungrounded() -> None:
    grounding = compute_grounding([])
    assert grounding.support is None
    assert grounding.counter is None
    assert grounding.cited is False
    assert grounding.headline == "ungrounded"


# --- the flagship walkthrough (plan §5 Phase 3 exit) ----------------------------------------------


def test_flagship_measuring_across_a_corner_reads_b_with_the_last_rung_open() -> None:
    """Claims 1–4 are exact measurements/evaluations (**B**); claim 5 awaits a proof."""
    claims_1_to_4 = [
        compute_grounding([tool_link("support", instrument, "result")])
        for instrument in (
            "geometry.coordinate_measure",
            "geometry.coordinate_measure",
            "calc.eval",
            "expr.compare",
        )
    ]
    assert [g.headline for g in claims_1_to_4] == ["B", "B", "B", "B"]
    assert compute_grounding([]).headline == "ungrounded"  # claim 5


# --- 0.16.1: the yield measure (pure diff of two snapshots) ---------------------------------------


def _at(*links: tuple[str, str, dict[str, Any]]) -> ClaimGrounding:
    """A claim's grounding built from the same link builders used above."""
    return compute_grounding(list(links))


def test_a_pass_that_mints_but_raises_nothing_reads_moved_zero() -> None:
    """Acceptance 4 — the headline case of the whole release.

    Three claims measured, three checkpoints could have landed, and the ladder did not move. This
    must be recorded as *nothing bought*, not hidden behind a non-zero ``ran_count``.
    """
    ids = [uuid4() for _ in range(3)]
    before = {i: _at(tool_link("support", "calc.eval", "result")) for i in ids}
    # Each claim genuinely acquired a *new* evidence row this pass — the instruments ran and the
    # checkpoints landed. But every one came back ``undecided``, which earns no grade (honesty
    # rule 1), so the ladder is exactly where it was. Modelling the new row rather than reusing the
    # ``before`` map is the point: this must fail if ``undecided`` ever starts contributing a rung.
    after = {
        i: _at(
            tool_link("support", "calc.eval", "result"),
            tool_link("support", "z3.prove", "undecided"),
        )
        for i in ids
    }

    result = compute_yield(ids, before, after)

    assert result.measured == 3
    assert result.moved == 0
    assert result.changed == []


def test_ungrounded_to_proven_is_settled() -> None:
    """Acceptance 5 — a claim that had nothing and now carries a machine-checked proof."""
    claim_id = uuid4()
    result = compute_yield(
        [claim_id], {}, {claim_id: _at(tool_link("support", "z3.prove", "result"))}
    )

    assert result.moved == 1
    entry = result.changed[0]
    assert (entry.before, entry.after, entry.movement) == ("ungrounded", "proven", "settled")


def test_b_to_refuted_is_settled_never_a_regression() -> None:
    """Acceptance 6 — a refutation is a *successful* research outcome, not a downgrade.

    Comparing headline strings (or support rungs) would call this a loss. It is the pass's best
    possible result: the claim is now decided.
    """
    claim_id = uuid4()
    before = {claim_id: _at(tool_link("support", "calc.eval", "result"))}
    after = {
        claim_id: _at(
            tool_link("support", "calc.eval", "result"),
            tool_link("weaken", "counterexample.search", "refuted"),
        )
    }
    result = compute_yield([claim_id], before, after)

    entry = result.changed[0]
    assert (entry.before, entry.after, entry.movement) == ("B", "refuted", "settled")
    assert result.moved == 1


def test_c_to_b_is_a_raise() -> None:
    """Sampling hardened into an exact result — the ladder's ordinary rung climb."""
    claim_id = uuid4()
    result = compute_yield(
        [claim_id],
        {claim_id: _at(tool_link("support", "counterexample.search", "result"))},
        {claim_id: _at(tool_link("support", "expr.compare", "result"))},
    )

    entry = result.changed[0]
    assert (entry.before, entry.after, entry.movement) == ("C", "B", "raised")
    assert result.moved == 1


def test_a_claim_with_no_evidence_on_either_side_is_still_measured() -> None:
    """The ids drive the diff, not the maps' keys — an untouched empty claim still counts.

    If the maps drove it, the claim a pass most wants to move (one with nothing recorded) would be
    invisible on both sides, and ``measured`` would understate what the pass had to work with.
    """
    ids = [uuid4(), uuid4()]
    result = compute_yield(ids, {}, {})
    assert result.measured == 2
    assert result.moved == 0


def test_a_new_pin_is_recorded_but_does_not_count_as_moved() -> None:
    """Off-ladder stays off-ladder: a citation is a real change, but it climbs no rung."""
    claim_id = uuid4()
    result = compute_yield([claim_id], {}, {claim_id: _at(pin_link("support"))})

    assert result.moved == 0  # ``cited`` is not a rung
    entry = result.changed[0]
    assert (entry.before, entry.after, entry.movement) == ("ungrounded", "cited", "unchanged")


def test_an_already_proven_claim_cannot_move_again() -> None:
    """A settled claim stays settled — the second proof buys nothing, and says so."""
    claim_id = uuid4()
    proven = _at(tool_link("support", "z3.prove", "result"))
    result = compute_yield([claim_id], {claim_id: proven}, {claim_id: proven})
    assert result.moved == 0


def test_a_proof_overturned_by_a_counterexample_is_decisive_movement() -> None:
    """0.16.2 regression — the most consequential event the ledger can record must not read as nil.

    A claim carrying a machine-checked proof acquires an exact counterexample: the headline goes
    ``proven → refuted`` while the *support* rung never moves (the proof is still linked). Under the
    original ``before.headline not in SETTLED`` guard this failed the settled branch, failed the
    rank branch, and scored ``unchanged`` — so a pass that overturned a proof reported ``moved: 0``
    and the trace stated in words that no claim's grounding moved.

    A contradiction between a proof and a witness is decisive movement in either direction; only a
    transition to the *same* headline is not.
    """
    claim_id = uuid4()
    proof = tool_link("support", "z3.prove", "result")
    result = compute_yield(
        [claim_id],
        {claim_id: _at(proof)},
        {claim_id: _at(proof, tool_link("weaken", "counterexample.search", "refuted"))},
    )

    assert result.moved == 1
    entry = result.changed[0]
    assert (entry.before, entry.after, entry.movement) == ("proven", "refuted", "settled")


def test_a_refutation_later_proved_is_also_decisive() -> None:
    """The mirror direction, so the fix is not read as a one-way special case."""
    claim_id = uuid4()
    result = compute_yield(
        [claim_id],
        {claim_id: _at(tool_link("weaken", "counterexample.search", "refuted"))},
        {claim_id: _at(tool_link("support", "z3.prove", "result"))},
    )

    entry = result.changed[0]
    assert (entry.before, entry.after, entry.movement) == ("refuted", "proven", "settled")


def test_nothing_measured_is_a_valid_empty_measure() -> None:
    """A thread with no open claims: the pass had nothing to move, and the record says so."""
    result = compute_yield([], {}, {})
    assert (result.measured, result.moved, result.changed) == (0, 0, [])
