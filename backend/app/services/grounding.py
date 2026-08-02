"""Claim grounding — the evidence axis of the claim read model (0.16.0).

``compute_signal`` (``services/claims.py``) answers *"what did assessors conclude?"*. This module
answers the other half: *"how strongly is this claim backed by what actually ran?"* — so that
``primitives.md``'s promise (*confidence explainable through evidence and validation history, not a
naked score*) is true of the **evidence** half too. Before this, a claim carrying a ``z3.prove``
machine-checked proof and a claim carrying nothing but an opinion both read ``signal: "none"`` until
a human clicked *validate*.

**Derived, never stamped** (plan D1). No caller may set a grade; it is a consequence of the recorded
run. **No schema work** (D2): the whole chain already exists — this adds consumers, not structure.

The traversal, one join deep::

    Claim
      └─ ClaimEvidenceLink.relation_kind ∈ {support, weaken, context}
           └─ Evidence.source_type        "tool" | "oeis" | (anything, for hand-attached rows)
              Evidence.evidence_metadata  {output, status, instrument}   ← the grade is read here

Reading ``evidence_metadata`` rather than the blame tuple is an **accepted denormalization** (D3 /
R2). The authoritative record stays the ``ToolInvocation`` on the append-only ``Checkpoint``, but it
rides as JSON inside a blob and reaching it per claim would mean walking
``CheckpointRef → Checkpoint → tool_invocations[] → produced_artifact_id → EvidenceArtifactLink``.
``tool_runs.py`` writes both in the **same transaction** and nothing else writes either, so the copy
is correct by construction. If a divergence is ever observed the fix is to read the blame tuple —
never to stamp a grade.
"""

from collections import defaultdict
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import EvidenceGrade, ResultStatus
from app.models.evidence import Evidence
from app.models.links import ClaimEvidenceLink
from app.schemas.agent_run import ClaimMovement, ClaimYield, PassYield
from app.schemas.claim import ClaimGrounding, GroundingHeadline
from app.toolbench.grading import grade_for, outranks, strongest

# The ``Evidence.source_type`` a *compute* instrument's evidence carries (``tool_runs.py``:
# ``source_type = result.source_type or "tool"``). A retrieval instrument overrides it with its
# provider ("oeis"), which is exactly how D7 discriminates off-ladder evidence from graded evidence.
_COMPUTE_SOURCE_TYPE = "tool"

# Relation kinds that feed each side of the grounding (``context`` feeds neither — it is the default
# an ``undecided`` run lands under, and rule 1 says undecided contributes nothing).
_SUPPORT = "support"
_COUNTER = "weaken"

# A counter at or above this rung *settles* the claim negatively and dominates any support (D8).
# C/D counters deliberately do not: finite sampling and a human assertion contest a claim, they do
# not refute it — that distinction is the validation axis's job (``signal: "contested"``), not this
# one's.
_DOMINATING_COUNTERS = frozenset({EvidenceGrade.A, EvidenceGrade.B})


def _grade_of_link(source_type: str, metadata: dict[str, Any] | None) -> EvidenceGrade | None:
    """The rung one evidence row earns — ``None`` when the outcome contributes nothing.

    The branch order matters and encodes honesty rules 1 and 2:

    - **No ``instrument`` key ⇒ Grade D.** A hand-attached evidence row is human-asserted: the
      baseline the bench exists to climb out of, legitimately D and never an error (rule 2).
    - **An ``instrument`` key ⇒ the matrix decides**, and ``None`` from the matrix stays ``None``.
      It must *not* fall through to D: D asserts "a human said so", which would be a false statement
      about a row a tool actually produced. An ``undecided`` run therefore contributes nothing
      (rule 1) rather than quietly landing on the bottom rung.
    - **Retrieval evidence is off-ladder** and is handled by the caller as ``cited`` (D7).
    """
    meta = metadata or {}
    instrument = meta.get("instrument")
    if not isinstance(instrument, str) or not instrument:
        return EvidenceGrade.D  # human-asserted — rule 2

    if source_type != _COMPUTE_SOURCE_TYPE:
        return None  # retrieval — off-ladder, surfaced as ``cited`` instead (D7)

    try:
        status = ResultStatus(meta.get("status"))
    except ValueError:
        # A tool-produced row whose status we cannot parse: grade nothing rather than guess. Never
        # D — the row is not human-asserted (R1: understating rigor is the recoverable direction).
        return None

    return grade_for(instrument, status)


def _is_live_pin(source_type: str, metadata: dict[str, Any] | None) -> bool:
    """Whether an evidence row is a real external citation (D7).

    Requires all three: an ``instrument`` (so a hand-attached ``source_type="paper"`` row stays
    Grade D per rule 2 rather than being promoted to ``cited``), a non-``tool`` ``source_type`` (the
    retrieval marker), and a **decided** outcome.

    That last condition is a deliberate tightening of the plan's §3.1 wording, which says only *"any
    link whose evidence.source_type is external"*. An ``oeis.search`` that finds no match returns
    ``undecided`` — a real pin of a *non-match*. Counting it would move a claim's headline from
    ``ungrounded`` up to ``cited``, i.e. let a failed lookup read as a weak pass, which is precisely
    what honesty rule 1 exists to prevent. The pin is still recorded on the ledger and still
    citable; it just does not raise the claim's rung.
    """
    meta = metadata or {}
    instrument = meta.get("instrument")
    if not isinstance(instrument, str) or not instrument:
        return False
    if source_type == _COMPUTE_SOURCE_TYPE:
        return False
    return meta.get("status") != ResultStatus.UNDECIDED.value


def _headline(
    support: EvidenceGrade | None, counter: EvidenceGrade | None, cited: bool
) -> GroundingHeadline:
    """The display precedence table (plan §3.1), as the one place the rules live.

    Server-side by decision (plan §8 Q2): keeping precedence in one testable place is worth carrying
    a discriminant in a read schema. It is a *discriminant*, not copy — every user-facing string is
    the client's.
    """
    if counter in _DOMINATING_COUNTERS:
        return "refuted"  # dominates any support (D8)
    if support is EvidenceGrade.A:
        return "proven"
    if support is not None:
        return support.value  # type: ignore[return-value]  # B / C / D are GroundingHeadline members
    if cited:
        return "cited"
    return "ungrounded"


def compute_grounding(
    links: list[tuple[str, str, dict[str, Any] | None]],
) -> ClaimGrounding:
    """Aggregate one claim's ``(relation_kind, source_type, evidence_metadata)`` rows (§3.1).

    Split out from the loader so the aggregation is unit-testable without a database.
    """
    support_grades: list[EvidenceGrade] = []
    counter_grades: list[EvidenceGrade] = []
    cited = False

    for relation_kind, source_type, metadata in links:
        if _is_live_pin(source_type, metadata):
            cited = True
        grade = _grade_of_link(source_type, metadata)
        if grade is None:
            continue
        if relation_kind == _SUPPORT:
            support_grades.append(grade)
        elif relation_kind == _COUNTER:
            counter_grades.append(grade)
        # ``context`` contributes to neither side, by design.

    support = strongest(support_grades)
    counter = strongest(counter_grades)
    return ClaimGrounding(
        support=support,
        counter=counter,
        cited=cited,
        headline=_headline(support, counter, cited),
    )


# --- 0.16.1: the yield measure --------------------------------------------------------------------

# Headlines whose evidence axis is *decided* — a machine-checked proof, or an exact counter that
# dominates any support (D8). Kept beside the precedence table it derives from; ``prompts.py`` holds
# the same frozenset for the planner's stop rule, both reading one ``GroundingHeadline`` union.
_SETTLED_HEADLINES = frozenset({"proven", "refuted"})


def _movement(before: ClaimGrounding, after: ClaimGrounding) -> ClaimMovement:
    """How one claim's evidence axis moved across a pass.

    Order matters. ``settled`` is tested first because reaching a decisive headline is the strongest
    thing that can happen and must not be mis-reported as a mere raise — and because ``refuted``
    often arrives *without* the support rung moving at all, so the rank test would miss it entirely.
    """
    if after.headline in _SETTLED_HEADLINES and before.headline not in _SETTLED_HEADLINES:
        return "settled"
    if outranks(after.support, before.support):
        return "raised"
    return "unchanged"


def compute_yield(
    claim_ids: list[UUID],
    before: dict[UUID, ClaimGrounding],
    after: dict[UUID, ClaimGrounding],
) -> PassYield:
    """Diff two grounding snapshots into the pass's yield (pure — the orchestrator does the I/O).

    ``claim_ids`` is passed explicitly rather than inferred from the maps' keys: a claim with no
    evidence links at all is *absent* from both, and it is precisely the claim a pass most wants to
    move. Reading the ids as the source of truth means a run that takes a claim from nothing to a
    proof is measured, instead of being invisible on both sides of the diff.
    """
    empty = ClaimGrounding()
    changed: list[ClaimYield] = []
    moved = 0

    for claim_id in claim_ids:
        was = before.get(claim_id) or empty
        now = after.get(claim_id) or empty
        movement = _movement(was, now)
        if movement != "unchanged":
            moved += 1
        # A headline can change without the claim "moving" (e.g. ungrounded → cited: a real pin, but
        # off-ladder). Record those too — the trace should show what happened, and ``moved`` is the
        # number that stays honest about rungs.
        if movement != "unchanged" or was.headline != now.headline:
            changed.append(
                ClaimYield(
                    claim_id=claim_id,
                    before=was.headline,
                    after=now.headline,
                    movement=movement,
                )
            )

    return PassYield(measured=len(claim_ids), moved=moved, changed=changed)


async def grounding_by_claim(
    db: AsyncSession, claim_ids: list[UUID]
) -> dict[UUID, ClaimGrounding]:
    """Batched: every claim's derived grounding, keyed by claim id.

    **One** query for the whole set, mirroring ``validations.validations_by_claim`` — the 0.4.4
    no-N+1 constraint (acceptance criterion 7). Claims with no evidence links are simply absent from
    the map; the caller substitutes an empty ``ClaimGrounding`` (which reads ``ungrounded``).
    """
    if not claim_ids:
        return {}

    result = await db.execute(
        select(
            ClaimEvidenceLink.claim_id,
            ClaimEvidenceLink.relation_kind,
            Evidence.source_type,
            Evidence.evidence_metadata,
        )
        .join(Evidence, Evidence.id == ClaimEvidenceLink.evidence_id)
        .where(ClaimEvidenceLink.claim_id.in_(claim_ids))
    )

    by_claim: dict[UUID, list[tuple[str, str, dict[str, Any] | None]]] = defaultdict(list)
    for claim_id, relation_kind, source_type, metadata in result:
        by_claim[claim_id].append((relation_kind, source_type, metadata))

    return {claim_id: compute_grounding(rows) for claim_id, rows in by_claim.items()}
