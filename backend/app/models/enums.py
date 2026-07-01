from enum import StrEnum


class ActorType(StrEnum):
    HUMAN = "human"
    AGENT = "agent"
    SYSTEM = "system"


class ProjectStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class ProjectRole(StrEnum):
    """Project-level authorization / governance (0.8.1) — deliberately *not* a credit role.

    Membership grants the *capability* to edit a project; it confers no authorship, validation, or
    funding credit (those stay on Contribution / Validation / FundingAllocation). ``OWNER`` is a
    superset of ``ADMIN`` — there is exactly one owner per project (enforced by a partial unique
    index); admins may edit metadata and invite further admins.
    """

    OWNER = "owner"
    ADMIN = "admin"


class InvitationStatus(StrEnum):
    """Lifecycle of a project collaboration invitation (0.8.7) — governance, not credit.

    An invite starts ``PENDING``; the invitee ``ACCEPTED``s it (gaining a ``ProjectMember`` row) or
    ``DECLINED``s it; an owner/admin may ``REVOKE`` a pending one. Re-inviting a declined/revoked
    user resets the *same* row to ``PENDING`` (there is one invitation row per project+invitee), so
    these are the four states a single row moves through — never a ledger event.
    """

    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    REVOKED = "revoked"


class ThreadStage(StrEnum):
    DECOMPOSE = "decompose"
    HYPOTHESIZE = "hypothesize"
    FORMALIZE = "formalize"
    DESIGN = "design"
    EXECUTE = "execute"
    VALIDATE = "validate"
    INTEGRATE = "integrate"


class ThreadStatus(StrEnum):
    OPEN = "open"
    ACTIVE = "active"
    BLOCKED = "blocked"
    DEAD_END = "dead_end"
    CLOSED = "closed"


class ClaimKind(StrEnum):
    HYPOTHESIS = "hypothesis"
    ASSUMPTION = "assumption"
    CONSTRAINT = "constraint"
    OBSERVATION = "observation"
    OBJECTION = "objection"
    RESULT = "result"
    RETRACTION = "retraction"


class ClaimStatus(StrEnum):
    PROPOSED = "proposed"
    SUPPORTED = "supported"
    CHALLENGED = "challenged"
    VALIDATED = "validated"
    RETRACTED = "retracted"


class FundingKind(StrEnum):
    TOP_UP = "top_up"
    GRANT = "grant"
    REFUND = "refund"
    ADJUSTMENT = "adjustment"


class FundingStatus(StrEnum):
    PENDING = "pending"
    SETTLED = "settled"
    FAILED = "failed"
    REFUNDED = "refunded"


class FundingSource(StrEnum):
    """Where the budget came from (0.6.3), orthogonal to FundingKind's accounting category.

    ``native`` = Kamino comps the budget against the platform's own (future) compute, gated to
    ``internal`` actors. ``stripe`` = an external funder pays (modeled; real settlement deferred).
    """

    NATIVE = "native"
    STRIPE = "stripe"


class BranchStatus(StrEnum):
    OPEN = "open"
    MERGED = "merged"
    CLOSED = "closed"
    DEAD_END = "dead_end"


class ValidationOutcome(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"
    NEEDS_REPRODUCTION = "needs_reproduction"
    CONTRADICTS = "contradicts"
    RETRACT = "retract"


class ResultStatus(StrEnum):
    """The three honest outcomes of a deterministic toolbench instrument run (0.9.1).

    Carried as a field inside the blame tuple on ``Checkpoint.tool_invocations`` (JSON) — **not** a
    DB column — so it stays a plain ``StrEnum`` serialised as its string value; promotion to a named
    Postgres enum is deferred until (and only if) it ever becomes a column (plan Decision;
    docs/executing/toolbench-provenance-and-first-instruments.md Phase 1).

    - ``RESULT``    — the instrument ran and produced a result.
    - ``REFUTED``   — the instrument ran and falsified the claim (a counterexample, e.g. ``5 ≠ 7``).
    - ``UNDECIDED`` — the instrument ran but could not decide (the seam to escalate to a deferred
      proof — never rendered as a pass).

    An instrument *exception* (it did not run) is not one of these: it mints no checkpoint and
    surfaces as an error, so only genuine, citable outcomes are recorded (plan Phase 3).
    """

    RESULT = "result"
    REFUTED = "refuted"
    UNDECIDED = "undecided"
