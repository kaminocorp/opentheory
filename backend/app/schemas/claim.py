from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ClaimKind, ClaimStatus, EvidenceGrade
from app.schemas.validation import ValidationRead

# Derived display signal for a claim (0.4.4, plan Decision #5). Computed from validation
# history; it does NOT mutate the stored ``Claim.status`` — confidence stays explainable.
#   contested  — has an unretracted contradicts/failed validation
#   validated  — has a passing validation and is not contested
#   none       — no decisive signal yet
ClaimSignal = Literal["none", "contested", "validated"]

# The headline rung a claim's grounding reads as (0.16.0). A **discriminant**, not copy: the server
# owns the precedence rules (one place, testable) and the client owns every user-facing string.
#   proven      — a machine-checked supporting result (Grade A)
#   refuted     — an A/B counter, which dominates any amount of support
#   B / C / D   — the strongest supporting rung, when it is not A
#   cited       — an external pin only, no computed grade (retrieval is off-ladder)
#   ungrounded  — nothing decisive on either side
GroundingHeadline = Literal["proven", "refuted", "B", "C", "D", "cited", "ungrounded"]


class ClaimGrounding(BaseModel):
    """How strongly a claim is backed by *what actually ran* — the evidence axis (0.16.0).

    Sits **beside** ``ClaimSignal``, never merged into it: ``signal`` is validation-derived (what
    assessors concluded), ``grounding`` is evidence-derived (what instruments computed). Combining
    them into one number would recreate exactly the "naked score" ``primitives.md`` forbids, so
    nothing anywhere does arithmetic across the two.

    Like ``signal``, this is **display-derived**: it never mutates ``Claim.status`` or
    ``Claim.confidence`` (plan D6), and it is computed in the service — never via
    ``from_attributes`` on the ORM.

    Two sides are carried, not one (plan D8): a claim with an exact counterexample is refuted no
    matter how many supporting runs are also linked, mirroring the ``contested`` precedence in
    ``compute_signal``.
    """

    support: EvidenceGrade | None = None
    counter: EvidenceGrade | None = None
    # True when a retrieval instrument landed a real pin against this claim (off-ladder, D7).
    cited: bool = False
    headline: GroundingHeadline = "ungrounded"


class ClaimBase(BaseModel):
    kind: ClaimKind
    status: ClaimStatus = ClaimStatus.PROPOSED
    statement: str = Field(min_length=1)
    rationale: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    claim_metadata: dict[str, Any] = Field(default_factory=dict)


class ClaimCreate(ClaimBase):
    """Create payload. ``thread_id`` (and the derived ``project_id``) come from the path."""


class ClaimRead(ClaimBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    thread_id: UUID | None
    created_at: datetime
    updated_at: datetime
    # Enriched (0.4.4): the claim's validation history (oldest first) and the derived
    # signal. Constructed explicitly in the service — never via from_attributes on the
    # ORM (which would lazy-load the ``Claim.validations`` relationship).
    validations: list[ValidationRead] = Field(default_factory=list)
    signal: ClaimSignal = "none"
    # The second, independent axis (0.16.0): evidence-derived grounding. Batch-loaded and computed
    # in the service alongside ``signal`` — see the note above; same no-lazy-load rule applies.
    grounding: ClaimGrounding = Field(default_factory=ClaimGrounding)
