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

    ``native`` = the platform comps the budget against its own (future) compute, gated to
    ``internal`` actors. ``stripe`` = an external funder pays (modeled; real settlement deferred).
    """

    NATIVE = "native"
    STRIPE = "stripe"


class BranchStatus(StrEnum):
    OPEN = "open"
    MERGED = "merged"
    CLOSED = "closed"
    DEAD_END = "dead_end"


class MergeResolution(StrEnum):
    """How a merge combined parallel lines (0.21.0) — recorded on the merge checkpoint.

    Not a Postgres enum: it lives in ``Checkpoint.content`` JSON (like ``ResultStatus``), so
    the vocabulary can evolve without a migration. ``coexist`` is deliberately absent — that
    outcome is *not merging* (siblings stay open until evidence breaks the tie).

    - ``clean`` — the lines agree; their claims are unified.
    - ``resolved`` — the lines disagreed; an explicit rationale records the decision.
      A resolved merge without a rationale is rejected (honesty: no silent overwrite).
    """

    CLEAN = "clean"
    RESOLVED = "resolved"


class TagKind(StrEnum):
    """Why a named pointer was pinned to a checkpoint (0.21.0).

    A tag is a lightweight immutable annotation, not a rewrite of the commit it names.
    ``name=`` is the Postgres type (``tag_kind``); labels follow this DB's convention
    (StrEnum **member names**).

    - ``milestone`` — a funding- or attribution-relevant moment.
    - ``validated`` — a result the project considers established.
    - ``retraction`` — the last-good commit before a bad result was integrated.
    """

    MILESTONE = "milestone"
    VALIDATED = "validated"
    RETRACTION = "retraction"


class ValidationOutcome(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"
    NEEDS_REPRODUCTION = "needs_reproduction"
    CONTRADICTS = "contradicts"
    RETRACT = "retract"


class OrchestrationRunStatus(StrEnum):
    """Lifecycle of one project-level research orchestration (0.22.0).

    Mutable like ``AgentRun`` — not a ledger primitive, not append-only. The sub-passes it
    commissions write the ledger through ``run_agent_pass``; this row only narrates which
    threads were selected, skipped, and why the loop stopped. There is no
    ``awaiting_review`` and the orchestrator never self-validates.
    """

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentRunStatus(StrEnum):
    """Lifecycle of one thin-agent pass (0.12.x) — a **mutable** live trace, not a ledger primitive.

    Unlike ``Checkpoint`` / ``Validation`` / ``FundingAllocation`` (append-only, ORM-guarded in
    ``models/append_only.py``), an ``AgentRun`` moves ``running`` → ``completed`` | ``failed`` in
    place as the background pass progresses. It records what the agent *attempted* and what landed
    on the ledger (through the chokepoint), so it is deliberately excluded from the append-only
    guards — the ledger writes it triggers are immutable; the trace narrating them is not.

    There is no ``awaiting_review`` (0.17.0). ``completed`` means the pass stands; human
    accept / reject / fork is opt-in audit, not a fourth lifecycle state.
    """

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ComputeDebitKind(StrEnum):
    """What a compute debit is billing (0.19.0) — accounting category, not a credit role.

    v1 records one debit per pass for the planning-call tokens (``planning``). The kind
    exists so a later iterative loop can add ``execution`` rows without a new table.
    Like ``FundingKind``, this is a named Postgres enum (``name=`` is the DB type).
    """

    PLANNING = "planning"
    EXECUTION = "execution"


class EvidenceGrade(StrEnum):
    """How rigorously a piece of evidence backs a claim — the grade ladder (0.16.0).

    **Derived, never stamped.** No caller may set a grade; it is a pure function of *what actually
    ran* — ``(instrument, status)`` — resolved by ``app/toolbench/grading.py``. A stamped grade
    would be an unverifiable assertion about rigor; a derived one is a consequence of the recorded
    run, the same philosophy as the append-only guard (``schemas/tool_invocation.py``: the grade is
    *"derivable from the recorded instrument, never stamped"*).

    - ``A`` — machine-checked (a Z3 proof or counter-model).
    - ``B`` — exact symbolic/arithmetic computation (equivalence, an exact measurement, an exact
      counterexample).
    - ``C`` — finite sampling; real support, but it settles nothing.
    - ``D`` — human-asserted or LLM-only: no instrument in the chain. **The absence of a tool, not a
      failure** — it is the baseline the bench exists to climb out of and must never render as an
      error.

    Retrieval (``oeis.search``, ``crossref.lookup``, ``arxiv.lookup``, ``openalex.lookup``) is
    deliberately **off-ladder**: a pin is graded by source authority,
    not by computation, so it reads ``cited`` rather than a letter (plan D7).

    Like ``ResultStatus``, this is a plain ``StrEnum`` and **not** a named Postgres type: grounding
    is a read-model derivation over existing rows (plan D2 — no column, no table, no migration), so
    promotion is deferred until (and only if) it ever becomes a column.
    """

    A = "A"
    B = "B"
    C = "C"
    D = "D"


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
