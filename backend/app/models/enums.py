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
