"""The bounded agent orchestrator (0.12.2 / 0.20.0) — one pass, executed on an agent branch.

``run_agent_pass`` is the loop's engine. It composes the reuse spine and invents **no** ledger
mechanics: it resolves the project's agent Actor, then runs a capped **plan → observe → replan**
loop. Each plan version is held to the fixed instrument catalog; each runnable step goes through
the **same** ``run_instrument`` chokepoint humans use — attributed to the agent Actor, on the
agent branch. Observations (instrument outcomes, whether anything minted, grounding deltas) feed
the next planning call. Every plan version and every step is recorded on the ``AgentRun`` trace;
a per-step failure is caught so one bad run never aborts the pass. Forking after the first
non-empty plan keeps a failed or empty pass free of any mint.

Three invariants this file must preserve:

- **One write path / failure split.** The loop reaches the ledger only via ``run_instrument`` (which
  runs the instrument *before* any ``db.add``, so a failure mints nothing) and ``create_branch``.
  A failed step is a recorded trace entry, not a checkpoint.
- **Sequence of atomic transactions, not one.** Each ``run_instrument`` → ``create_checkpoint`` owns
  its own commit, so a later failed step never rolls back an earlier durable result. The trace is
  therefore committed *separately* after each step (a mutable narrative alongside the immutable
  ledger).
- **JSON columns need reassignment.** ``AgentRun.steps`` / ``plan`` are plain ``JSON`` columns (no
  ``Mutable*``), so this file **reassigns** them a fresh object on every update — an in-place
  ``.append`` would be invisible to SQLAlchemy's dirty-tracking and silently lost.
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.llm import AgentLlmError, LlmClient, OpenRouterClient
from app.agent.observe import Observation, summarize_observations
from app.agent.planner import PlannedRun, PlanResult
from app.agent.planner import plan as default_plan
from app.agent.pricing import quote_model_price
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.actor import Actor
from app.models.agent_run import AgentRun
from app.models.branch import Branch
from app.models.claim import Claim
from app.models.enums import AgentRunStatus, BranchStatus
from app.models.project import Project
from app.models.thread import Thread
from app.schemas.branch import BranchCreate
from app.schemas.claim import ClaimGrounding
from app.services import branches as branch_service
from app.services import checkpoints as checkpoint_service
from app.services import claims as claim_service
from app.services import compute as compute_service
from app.services import funding as funding_service
from app.services.agent_actors import get_or_create_project_agent_actor
from app.services.compute import BUDGET_EXHAUSTED, BUDGET_EXHAUSTED_REASON, ProjectBudgetPolicy
from app.services.grounding import compute_yield, grounding_by_claim
from app.services.tool_runs import run_instrument
from app.toolbench.catalog import build_catalog
from app.toolbench.registry import registry

logger = logging.getLogger(__name__)

# The planner is injectable (a canned callable in tests). Its shape mirrors ``agent.planner.plan``.
PlannerFn = Callable[..., Awaitable[PlanResult]]


class BudgetPolicy(Protocol):
    """The budget seam (Decision #4). ``check`` returns ``True`` to keep going.

    Default (``None``) is the project ceiling (0.19.0 / historical ``0.12.5``): refuse to
    start when ``available <= 0``, debit recorded tokens, stop the instrument loop when
    the remainder is exhausted — and do not replan after a budget stop. The per-pass
    safety caps (``agent_pass_max_runs``, ``agent_pass_max_replans``,
    ``agent_pass_max_batch_runs``) still bound blast radius independently. The
    0.22.0 project orchestrator commissions sequential sub-passes against the
    shared project ceiling (it does not inject a per-thread slice — **no
    per-thread limits ever**).

    0.16.1 supplied the missing half of metering — the recorded ``AgentRun.grounding_yield`` —
    so a budget can ask "what did the last pass buy?" instead of only "how much did it spend?".
    """

    def check(self, *, tokens_used: int, ran_count: int) -> bool: ...


async def _open_claims(db: AsyncSession, thread_id: UUID) -> list[Claim]:
    """The thread's claims still in play on the validation axis (signal ≠ validated)."""
    return await claim_service.open_claims_for_planner(db, thread_id)


async def select_agent_branch(
    db: AsyncSession,
    project_id: UUID,
    thread_id: UUID,
    agent_actor: Actor,
    *,
    role: str,
) -> UUID | None:
    """Pick where this pass lands (Decision #2): reuse the open agent line, else fork, else main.

    1. **Reuse** — the newest ``OPEN`` branch referenced by any ``AgentRun`` on this thread (the
       ``agent_runs`` table is the provenance index for "which branches are agent branches"). This
       keeps a durable line of inquiry across passes instead of proliferating branches.
    2. **Fork** — else fork a fresh agent branch off the thread's latest main-line checkpoint,
       attributed to the agent Actor.
    3. **Main-line fallback** — else ``None`` (the thread has no forkable checkpoint yet).

    Known v1 limitation: two passes commissioned on the *same thread* nearly simultaneously can each
    reach the reuse query before the other has committed its ``branch_id``, so both fork — leaving
    two open agent lines on the thread. Unlike the agent-Actor race (closed by a partial unique
    index), there is no DB-level "one open agent line per thread" guard yet. It is non-destructive
    (branches are recorded, not deleted; the next pass reuses the newest open line), so it is
    accepted for the thin line; a durable-queue/serialized executor is the future fix.
    """
    reuse = await db.execute(
        select(Branch.id)
        .join(AgentRun, AgentRun.branch_id == Branch.id)
        .where(AgentRun.thread_id == thread_id, Branch.status == BranchStatus.OPEN)
        .order_by(Branch.created_at.desc())
        .limit(1)
    )
    existing = reuse.scalar_one_or_none()
    if existing is not None:
        return existing

    fork = await checkpoint_service.latest_thread_checkpoint(db, project_id, thread_id)
    if fork is None:
        return None

    branch = await branch_service.create_branch(
        db,
        project_id,
        BranchCreate(
            from_checkpoint_id=fork.id,
            thread_id=thread_id,
            name=f"Agent line · {role}"[:160],
            reason="agent pass",
        ),
        agent_actor,
    )
    return branch.id


def _executed_step(
    index: int, run: Any, *, status: str, plan_version: int = 0, **extra: Any
) -> dict[str, Any]:
    """A per-step trace entry (landed/failed), in the documented ``AgentRun`` step shape."""
    return {
        "index": index,
        "instrument": run.instrument,
        "inputs": run.inputs,
        "claim_id": str(run.claim_id) if run.claim_id is not None else None,
        "relation_kind": run.relation_kind,
        "rationale": run.rationale,
        "status": status,
        "checkpoint_id": extra.get("checkpoint_id"),
        "evidence_id": extra.get("evidence_id"),
        "outcome": extra.get("outcome"),
        "error": extra.get("error"),
        "reason": extra.get("reason"),
        "plan_version": plan_version,
    }


def _plan_step(
    *,
    version: int,
    reason: str,
    observe_summary: str | None,
    planned_runs: int,
    error: str | None = None,
) -> dict[str, Any]:
    """A narrative plan / replan row — mints nothing; the trace is not a black box."""
    return {
        "index": None,
        "instrument": "",
        "inputs": {},
        "claim_id": None,
        "relation_kind": None,
        "rationale": "",
        "status": "plan" if version == 0 else "replan",
        "checkpoint_id": None,
        "evidence_id": None,
        "outcome": None,
        "error": error,
        "reason": reason,
        "plan_version": version,
        "observe_summary": observe_summary,
        "planned_runs": planned_runs,
    }


def _version_record(
    version: int,
    plan_result: PlanResult,
    *,
    reason: str,
    observe_summary: str | None,
) -> dict[str, Any]:
    """One entry in ``AgentRun.plan["versions"]``."""
    return {
        "version": version,
        "runs": [run.model_dump(mode="json") for run in plan_result.runnable],
        "reason": reason,
        "observe_summary": observe_summary,
        "tokens_used": plan_result.tokens_used,
        "proposed_count": plan_result.proposed_count,
    }


def _plan_payload(versions: list[dict[str, Any]], latest_runs: list[PlannedRun]) -> dict[str, Any]:
    """Keep ``plan.runs`` as the latest version so pre-0.20.0 readers still see a plan."""
    return {
        "runs": [run.model_dump(mode="json") for run in latest_runs],
        "versions": list(versions),
    }


def _headline(grounding: dict[UUID, ClaimGrounding], claim_id: UUID | None) -> str | None:
    if claim_id is None:
        return None
    return (grounding.get(claim_id) or ClaimGrounding()).headline


def _batch_cap(remaining_runs: int) -> int:
    """How many runnable steps this plan version may propose.

    When replans are disabled the pass is the 0.12.x one-shot: the planner may use
    the whole remaining run budget. When replans are on, each version is capped so
    there is budget left to spend after observing.
    """
    if settings.agent_pass_max_replans <= 0:
        return max(0, remaining_runs)
    return max(0, min(remaining_runs, settings.agent_pass_max_batch_runs))


def requires_review(_agent_run: AgentRun | None = None) -> bool:
    """Whether a human must accept/reject/fork before the pass is done for the operator.

    Phase 1 autonomy (0.17.0): **never**. A successful pass's attributed checkpoints on the
    agent branch stand as soon as ``status`` is ``completed`` — there is no pending-review
    state, and this function is the contract the read model serializes so a client cannot
    invent one. Accept / reject / fork remain available as opt-in audit through the existing
    Validation and Branch write paths (they do not compose a second gate here). A failed or
    empty pass also does not wait: there is nothing to accept.

    The argument is accepted so a future policy can inspect the row without changing callers;
    it is unused on purpose.
    """
    return False


async def _finalize(
    db: AsyncSession,
    agent_run: AgentRun,
    *,
    status: AgentRunStatus,
    error: str | None = None,
) -> AgentRun:
    """Commit the current (maybe partial) trace with a terminal status. Never leaves ``running``.

    ``completed`` is operator-done (0.17.0): the pass's attributed checkpoints already stand
    on the agent branch. Human accept / reject / fork is opt-in audit after this commit, not
    a precondition of it — see :func:`requires_review`.
    """
    await compute_service.release_compute_reservation(db, agent_run)
    agent_run.status = status
    if error is not None:
        agent_run.error = error[:2000]
    await db.commit()
    return agent_run


async def run_agent_pass(
    db: AsyncSession,
    agent_run_id: UUID,
    *,
    llm: LlmClient | None = None,
    planner: PlannerFn = default_plan,
    budget_policy: BudgetPolicy | None = None,
) -> AgentRun:
    """Execute the pass identified by ``agent_run_id`` (a pre-created ``running`` row).

    Reads all context (``project_id`` / ``thread_id`` / ``role`` / ``triggered_by``) from the row —
    the single source of truth — so the 0.12.3 background entrypoint need only hand over the id.
    Any unexpected failure is caught and recorded as ``status=failed`` (never a dangling ``running``
    row, never a ``500`` to the caller).
    """
    agent_run = await db.get(AgentRun, agent_run_id)
    if agent_run is None:
        raise ValueError(f"AgentRun {agent_run_id} not found")

    try:
        return await _execute(db, agent_run, llm=llm, planner=planner, budget_policy=budget_policy)
    except Exception as exc:  # truly unexpected — roll back the partial tail, record a failed trace
        logger.warning("agent_pass_unexpected_error agent_run_id=%s error=%s", agent_run_id, exc)
        await db.rollback()
        reloaded = await db.get(AgentRun, agent_run_id)
        if reloaded is None:  # pragma: no cover - the row was committed before we were called
            raise
        return await _finalize(db, reloaded, status=AgentRunStatus.FAILED, error=str(exc))


async def _execute(
    db: AsyncSession,
    agent_run: AgentRun,
    *,
    llm: LlmClient | None,
    planner: PlannerFn,
    budget_policy: BudgetPolicy | None,
) -> AgentRun:
    project = await db.get(Project, agent_run.project_id)
    thread = await db.get(Thread, agent_run.thread_id)
    if project is None or thread is None:
        return await _finalize(
            db, agent_run, status=AgentRunStatus.FAILED, error="project or thread not found"
        )

    # 1. Resolve the agent Actor (lazily created, idempotent) and stamp it on the trace.
    agent_actor = await get_or_create_project_agent_actor(db, agent_run.project_id)
    agent_run.agent_actor_id = agent_actor.id

    # 2. Resolve the role's model. An unassigned role is a recorded failed trace (mints nothing) —
    #    not a 500, not a commission-time reject (the plan wants it visible on the trace).
    model = (project.agent_models or {}).get(agent_run.role)
    if not model:
        return await _finalize(
            db,
            agent_run,
            status=AgentRunStatus.FAILED,
            error=f"role '{agent_run.role}' has no model assigned",
        )
    agent_run.model = model

    # 2b. Project ceiling (0.19.0 / 0.27.0 / 0.28.0). An injected BudgetPolicy
    #     replaces the default so tests and the orchestrator can supply a reserved
    #     slice. The default reserves against the live project pot and refuses
    #     *before* the planner so an exhausted project never spends. A hold
    #     already on the row (orchestrator reserved it) is reused, not stacked.
    #     0.28.0: the rate comes from a live OpenRouter quote when the catalog
    #     is reachable; otherwise the blended fallback. Same quote is reused on
    #     the debit and on the reservation envelope.
    price_quote = await quote_model_price(model)
    enforce_project_ceiling = budget_policy is None
    rate = price_quote.effective_rate_per_1k
    if budget_policy is None:
        reserved = agent_run.reserved_amount
        if reserved is None or reserved <= 0:
            opening = await funding_service.project_budget(db, agent_run.project_id)
            if opening.available <= 0:
                return await _finalize(
                    db, agent_run, status=AgentRunStatus.FAILED, error=BUDGET_EXHAUSTED
                )
            reserved = await compute_service.reserve_compute_for_pass(
                db, agent_run, rate_per_1k=rate
            )
            if reserved is None:
                return await _finalize(
                    db, agent_run, status=AgentRunStatus.FAILED, error=BUDGET_EXHAUSTED
                )
            await db.commit()
        budget_policy = ProjectBudgetPolicy(Decimal(reserved), rate_per_1k=rate)

    # 3. Plan → observe → replan. The *initial* planning call happens BEFORE any branch fork, so a
    #    planner failure (down provider / unparseable plan) is a recorded failed trace that mints
    #    nothing at all. Later replan failures do not fail a pass that already landed work.
    #
    #    The grounding snapshot (0.16.1) loaded here is the ``before`` half of the yield measure
    #    (the whole pass, not one batch). Each replan re-reads grounding so a settled claim is
    #    visible to the next plan — that live snapshot is *not* the yield's ``before``.
    open_claims = await _open_claims(db, agent_run.thread_id)
    claim_ids = [claim.id for claim in open_claims]
    grounding_before = await grounding_by_claim(db, claim_ids)
    the_llm: LlmClient = llm if llm is not None else OpenRouterClient()

    remaining_runs = settings.agent_pass_max_runs
    remaining_replans = settings.agent_pass_max_replans
    catalog = build_catalog()

    async def _plan(
        *,
        grounding: dict[UUID, ClaimGrounding],
        observations: list[Observation] | None,
        claims: list[Claim],
    ) -> PlanResult:
        return await planner(
            thread,
            claims,
            catalog,
            model,
            llm=the_llm,
            max_runs=_batch_cap(remaining_runs),
            grounding=grounding,
            observations=observations,
        )

    try:
        plan_result = await _plan(
            grounding=grounding_before, observations=None, claims=open_claims
        )
    except AgentLlmError as exc:
        agent_run.tokens_used = getattr(exc, "tokens_used", 0)
        await compute_service.record_compute_debit(
            db,
            project_id=agent_run.project_id,
            agent_run_id=agent_run.id,
            tokens_used=agent_run.tokens_used,
            model=model,
            prompt_tokens=getattr(exc, "prompt_tokens", None),
            completion_tokens=getattr(exc, "completion_tokens", None),
            quote=price_quote,
        )
        await compute_service.release_compute_reservation(db, agent_run)
        return await _finalize(
            db, agent_run, status=AgentRunStatus.FAILED, error=f"planner failed: {exc}"
        )

    versions: list[dict[str, Any]] = [
        _version_record(0, plan_result, reason="initial", observe_summary=None)
    ]
    steps: list[dict[str, Any]] = [
        _plan_step(
            version=0,
            reason="initial",
            observe_summary=None,
            planned_runs=len(plan_result.runnable),
        ),
        *({**dropped, "plan_version": 0} for dropped in plan_result.dropped),
    ]
    planned_count = plan_result.proposed_count
    tokens_used = plan_result.tokens_used
    agent_run.plan = _plan_payload(versions, plan_result.runnable)
    agent_run.planned_count = planned_count
    agent_run.tokens_used = tokens_used
    agent_run.steps = list(steps)
    # Debit the recorded tokens now — the provider already billed the planning call. A zero-token
    # stub (tests) writes nothing. Idempotent on the agent_run_id unique index.
    await compute_service.record_compute_debit(
        db,
        project_id=agent_run.project_id,
        agent_run_id=agent_run.id,
        tokens_used=agent_run.tokens_used,
        model=model,
        prompt_tokens=plan_result.prompt_tokens,
        completion_tokens=plan_result.completion_tokens,
        quote=price_quote,
    )
    # Convert the hold into the debit so ``available`` does not double-count
    # this pass (spent already includes it).
    await compute_service.release_compute_reservation(db, agent_run)
    await db.commit()

    # 4. Select the agent branch (reuse / fork / main-line fallback) — but ONLY now that we know a
    #    run will actually land. Forking mints a branch-creation checkpoint, so an empty plan (0
    #    runnable), a planner failure, or a budget stop that will skip every step never creates a
    #    stray branch. Reuse across passes is a query (mints nothing) and still resolves the
    #    durable agent line.
    branch_id: UUID | None = None
    can_land = bool(plan_result.runnable)
    if can_land and budget_policy is not None:
        can_land = budget_policy.check(tokens_used=agent_run.tokens_used, ran_count=0)
    if can_land and enforce_project_ceiling:
        remaining = await funding_service.project_budget(db, agent_run.project_id)
        can_land = remaining.available > 0
    if plan_result.runnable and can_land:
        branch_id = await select_agent_branch(
            db, agent_run.project_id, agent_run.thread_id, agent_actor, role=agent_run.role
        )
        agent_run.branch_id = branch_id
        await db.commit()

    # 5. Execute the current plan version, observe, replan while budget remains. Each landed run
    #    is its own atomic transaction; a per-step failure is caught and recorded (mints nothing).
    ran_count = 0
    observations: list[Observation] = []
    step_index = 0
    plan_version = 0
    grounding_now = grounding_before

    async def _budget_exhausted() -> bool:
        if budget_policy is not None and not budget_policy.check(
            tokens_used=tokens_used, ran_count=ran_count
        ):
            return True
        if enforce_project_ceiling:
            remaining = await funding_service.project_budget(db, agent_run.project_id)
            if remaining.available <= 0:
                return True
        return False

    while True:
        batch = plan_result.runnable[:_batch_cap(remaining_runs)]
        if not batch:
            break

        batch_observations: list[Observation] = []
        budget_stop = False
        for run_i, run in enumerate(batch):
            if remaining_runs <= 0:
                break
            if await _budget_exhausted():
                # Record every remaining step in this batch so the trace shows what the
                # ceiling cut, not just the first one the loop happened to be on.
                # Do not replan after a budget stop — the pot is empty.
                for later_run in batch[run_i:]:
                    steps.append(
                        _executed_step(
                            step_index,
                            later_run,
                            status="skipped",
                            reason=BUDGET_EXHAUSTED_REASON,
                            plan_version=plan_version,
                        )
                    )
                    step_index += 1
                agent_run.steps = list(steps)
                await db.commit()
                budget_stop = True
                break

            remaining_runs -= 1  # the attempt itself — failed runs still cost the cap
            instrument = registry.get(run.instrument)
            if instrument is None:  # pragma: no cover - the planner already resolved it
                obs = Observation(
                    instrument=run.instrument,
                    status="failed",
                    claim_id=run.claim_id,
                    minted=False,
                    grounding_before=_headline(grounding_now, run.claim_id),
                )
                observations.append(obs)
                batch_observations.append(obs)
                steps.append(
                    _executed_step(
                        step_index,
                        run,
                        status="failed",
                        error="instrument not found",
                        plan_version=plan_version,
                    )
                )
                step_index += 1
                agent_run.steps = list(steps)
                await db.commit()
                continue

            try:
                result = await run_instrument(
                    db,
                    agent_run.project_id,
                    instrument,
                    agent_actor,
                    inputs=run.inputs,
                    thread_id=agent_run.thread_id,
                    branch_id=branch_id,
                    claim_id=run.claim_id,
                    relation_kind=run.relation_kind,
                )
            except HTTPException as exc:
                # The failure split: run_instrument raised before any db.add, so nothing was minted.
                obs = Observation(
                    instrument=run.instrument,
                    status="failed",
                    claim_id=run.claim_id,
                    minted=False,
                    grounding_before=_headline(grounding_now, run.claim_id),
                    error=str(exc.detail),
                )
                observations.append(obs)
                batch_observations.append(obs)
                steps.append(
                    _executed_step(
                        step_index,
                        run,
                        status="failed",
                        error=str(exc.detail),
                        plan_version=plan_version,
                    )
                )
                step_index += 1
                agent_run.steps = list(steps)
                await db.commit()
                continue

            ran_count += 1
            after_map = grounding_now
            movement = None
            if run.claim_id is not None:
                after_map = await grounding_by_claim(db, [run.claim_id])
                batch_yield = compute_yield([run.claim_id], grounding_now, after_map)
                movement = batch_yield.changed[0].movement if batch_yield.changed else "unchanged"
            before_headline = _headline(grounding_now, run.claim_id)
            after_headline = _headline(after_map, run.claim_id)
            obs = Observation(
                instrument=run.instrument,
                status="landed",
                outcome=result.status.value,
                claim_id=run.claim_id,
                checkpoint_id=str(result.checkpoint.id),
                minted=True,
                grounding_before=before_headline,
                grounding_after=after_headline,
                movement=movement,
            )
            observations.append(obs)
            batch_observations.append(obs)
            if run.claim_id is not None:
                grounding_now = {**grounding_now, **after_map}
            steps.append(
                _executed_step(
                    step_index,
                    run,
                    status="landed",
                    plan_version=plan_version,
                    checkpoint_id=str(result.checkpoint.id),
                    evidence_id=str(result.evidence_id) if result.evidence_id is not None else None,
                    outcome=result.status.value,
                )
            )
            step_index += 1
            agent_run.ran_count = ran_count
            agent_run.steps = list(steps)
            await db.commit()
            logger.info(
                "agent_pass_step_landed agent_run_id=%s instrument=%s checkpoint_id=%s outcome=%s",
                agent_run.id,
                run.instrument,
                result.checkpoint.id,
                result.status.value,
            )

        if budget_stop or remaining_runs <= 0 or remaining_replans <= 0:
            if remaining_runs > 0 and remaining_replans <= 0 and not budget_stop:
                steps.append(
                    {
                        "index": None,
                        "instrument": "pass",
                        "inputs": {},
                        "claim_id": None,
                        "relation_kind": None,
                        "rationale": "",
                        "status": "skipped",
                        "checkpoint_id": None,
                        "evidence_id": None,
                        "outcome": None,
                        "error": None,
                        "reason": "max_replans",
                        "plan_version": plan_version,
                    }
                )
                agent_run.steps = list(steps)
                await db.commit()
            break

        # Observe, then replan. A failed replan after landed work completes the pass — it must
        # not invert "one bad step never aborts the pass" on a narrative LLM call.
        open_claims = await _open_claims(db, agent_run.thread_id)
        live_ids = [claim.id for claim in open_claims]
        try:
            grounding_now = await grounding_by_claim(db, live_ids or claim_ids)
        except Exception as exc:  # observation is narrative — keep going with the last snapshot
            logger.warning(
                "agent_pass_observe_grounding_failed agent_run_id=%s error=%s",
                agent_run.id,
                exc,
                exc_info=True,
            )
            await db.rollback()
            reloaded = await db.get(AgentRun, agent_run.id)
            if reloaded is None:  # pragma: no cover
                raise
            agent_run = reloaded

        observe_summary = summarize_observations(batch_observations)
        remaining_replans -= 1
        plan_version += 1
        try:
            plan_result = await _plan(
                grounding=grounding_now,
                observations=observations,
                claims=open_claims,
            )
        except AgentLlmError as exc:
            tokens_used += getattr(exc, "tokens_used", 0)
            agent_run.tokens_used = tokens_used
            steps.append(
                _plan_step(
                    version=plan_version,
                    reason="planner_failed",
                    observe_summary=observe_summary,
                    planned_runs=0,
                    error=str(exc),
                )
            )
            agent_run.steps = list(steps)
            await db.commit()
            logger.warning(
                "agent_pass_replan_failed agent_run_id=%s error=%s", agent_run.id, exc
            )
            break

        tokens_used += plan_result.tokens_used
        planned_count += plan_result.proposed_count
        versions.append(
            _version_record(
                plan_version,
                plan_result,
                reason="replan",
                observe_summary=observe_summary,
            )
        )
        steps.append(
            _plan_step(
                version=plan_version,
                reason="replan",
                observe_summary=observe_summary,
                planned_runs=len(plan_result.runnable),
            )
        )
        steps.extend({**dropped, "plan_version": plan_version} for dropped in plan_result.dropped)
        agent_run.plan = _plan_payload(versions, plan_result.runnable)
        agent_run.planned_count = planned_count
        agent_run.tokens_used = tokens_used
        agent_run.steps = list(steps)
        await db.commit()
        logger.info(
            "agent_pass_replan agent_run_id=%s version=%s runnable=%s observe=%s",
            agent_run.id,
            plan_version,
            len(plan_result.runnable),
            observe_summary,
        )

        if plan_result.runnable and branch_id is None:
            branch_id = await select_agent_branch(
                db, agent_run.project_id, agent_run.thread_id, agent_actor, role=agent_run.role
            )
            agent_run.branch_id = branch_id
            await db.commit()

    agent_run.ran_count = ran_count
    agent_run.tokens_used = tokens_used
    agent_run.planned_count = planned_count
    agent_run.steps = list(steps)

    # 6. Measure the yield (0.16.1): re-read grounding for the same claims and diff it against the
    #    pre-plan snapshot. Every landed step has already committed, so this reads the pass's own
    #    durable effect. It is deliberately measured for *every* completed pass, including one that
    #    ran nothing — "measured 4, moved 0" is the honest record of a pass that bought nothing, and
    #    it is the number metering reads beside the debit (see BudgetPolicy / 0.19.0).
    #
    #    Guarded (0.16.2): the yield is *narrative*, like ``steps``, while the checkpoints this pass
    #    landed are already durable and committed. Letting a failed measurement reach the caller's
    #    catch-all would roll back the tail and mark a pass ``failed`` that in fact landed all it
    #    planned — inverting this file's own "one bad step never aborts the pass" invariant on the
    #    least important step of all. An unmeasurable pass records no measure and says so.
    agent_run_id = agent_run.id  # captured before a rollback can expire the instance
    try:
        grounding_after = await grounding_by_claim(db, claim_ids)
        agent_run.grounding_yield = compute_yield(
            claim_ids, grounding_before, grounding_after
        ).model_dump(mode="json")
        logger.info(
            "agent_pass_yield agent_run_id=%s ran=%s measured=%s moved=%s",
            agent_run_id,
            ran_count,
            agent_run.grounding_yield.get("measured"),
            agent_run.grounding_yield.get("moved"),
        )
    except Exception as exc:  # measurement is narrative — never let it fail a landed pass
        logger.warning(
            "agent_pass_yield_failed agent_run_id=%s error=%s", agent_run_id, exc, exc_info=True
        )
        # A DB failure leaves the session needing a rollback before anything else can run. That
        # discards only *pending* state: ``ran_count`` and ``steps`` were already committed by the
        # per-step loop, so the re-fetched row carries the full trace — just no measure. Re-fetched
        # by id (never by attribute access) because rollback expires the instance, and an expired
        # attribute read outside the greenlet would raise instead of reloading.
        await db.rollback()
        reloaded = await db.get(AgentRun, agent_run_id)
        if reloaded is None:  # pragma: no cover - the row was committed long before this point
            raise
        agent_run = reloaded
    return await _finalize(db, agent_run, status=AgentRunStatus.COMPLETED)


# --- 0.12.3: the commission entrypoint + background execution -------------------------------------


async def start_agent_pass(
    db: AsyncSession,
    project_id: UUID,
    thread_id: UUID,
    *,
    triggered_by: Actor,
    role: str,
    commit: bool = True,
) -> AgentRun:
    """Mint the ``running`` trace row in the **request** session (the ``POST`` half).

    ``commit=True`` (the default) commits so the ``202`` response can return a
    durable id. The orchestrator passes ``commit=False`` so it can write a
    reservation hold in the same transaction.

    Deliberately does *only* the commission: validate the thread belongs to the project (``404``
    otherwise) and record who/what/which-role, so the route can return ``202`` + a pollable id
    immediately. The pass itself — the multi-second LLM call and the instrument runs — happens later
    in :func:`run_agent_pass_background` (its own session). ``role`` validity is enforced upstream
    by ``AgentRunTrigger``; an *unassigned* role is intentionally not rejected here — it becomes a
    recorded ``failed`` trace inside the pass (Decision #7).
    """
    thread = await db.get(Thread, thread_id)
    if thread is None or thread.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")

    agent_run = AgentRun(
        project_id=project_id,
        thread_id=thread_id,
        triggered_by_actor_id=triggered_by.id,
        role=role,
        status=AgentRunStatus.RUNNING,
    )
    db.add(agent_run)
    if commit:
        await db.commit()
    else:
        await db.flush()
    return agent_run


@dataclass
class BackgroundExecutor:
    """The seam :func:`run_agent_pass_background` resolves **at call time** (see below).

    The pass runs *after* the commissioning ``POST`` returned ``202`` and its request session
    closed, so it must open its **own** session — from ``session_factory``. Production keeps every
    default: the app engine (``AsyncSessionLocal``), the real planner, and a live
    ``OpenRouterClient`` (constructed inside ``run_agent_pass`` when ``llm is None``). A DB-backed
    route test rebinds this *one* object (``monkeypatch.setattr(agent_runs, "background_executor",
    BackgroundExecutor(session_factory=…, planner=stub))``) so the background pass runs against the
    **test** engine with a stub planner and no OpenRouter key — the ``FastAPI`` ``BackgroundTask``
    cannot otherwise reach the test session.
    """

    session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal
    planner: PlannerFn = default_plan
    llm: LlmClient | None = None


background_executor = BackgroundExecutor()


async def run_agent_pass_background(agent_run_id: UUID) -> None:
    """FastAPI ``BackgroundTask`` entrypoint: run the pass in a fresh session; never let it escape.

    ``run_agent_pass`` already guards its own body and finalizes ``failed`` on any error inside the
    pass, so on the normal path this wrapper only opens the session and hands off. But a background
    task that *raised* would be swallowed by the server and strand the row ``running`` forever, so
    this additionally catches the pathological cases **outside** that guard — a missing row, a
    broken session — and best-effort marks the row ``failed`` in a clean session. The stale-run
    sweep on read (:func:`get_agent_run`) is the final backstop even if this too fails.
    """
    executor = background_executor
    try:
        async with executor.session_factory() as db:
            await run_agent_pass(db, agent_run_id, llm=executor.llm, planner=executor.planner)
        return
    except Exception:
        logger.exception("agent_pass_background_crashed agent_run_id=%s", agent_run_id)

    try:
        async with executor.session_factory() as db:
            agent_run = await db.get(AgentRun, agent_run_id)
            if agent_run is not None and agent_run.status is AgentRunStatus.RUNNING:
                await compute_service.release_compute_reservation(db, agent_run)
                agent_run.status = AgentRunStatus.FAILED
                agent_run.error = "background pass crashed unexpectedly"
                await db.commit()
    except Exception:
        logger.exception("agent_pass_background_finalize_failed agent_run_id=%s", agent_run_id)


# --- 0.12.3: reads (list + poll) with a stale-``running`` sweep -----------------------------------

# A ``running`` row whose ``updated_at`` predates this margin *plus* the worst-case pass wall-clock
# is treated as lost (a killed/restarted worker). A live pass keeps bumping ``updated_at`` on every
# per-step commit, so the sweep can never catch one that is genuinely in flight.
_STALE_RUN_MARGIN_S = 30.0


def _stale_running_cutoff() -> datetime:
    """The instant before which an untouched ``running`` row counts as lost.

    Worst-case wall-clock for a legitimate pass = every planning call (initial + max replans)
    + up to ``agent_pass_max_runs`` instrument runs (each bounded by ``toolbench_wall_timeout_s``)
    + a margin. Anything ``running`` and untouched for longer than that had its worker die.
    """
    ttl = (
        settings.agent_llm_timeout_s * (1 + settings.agent_pass_max_replans)
        + settings.agent_pass_max_runs * settings.toolbench_wall_timeout_s
        + _STALE_RUN_MARGIN_S
    )
    return datetime.now(UTC) - timedelta(seconds=ttl)


def _sweep_if_stale(agent_run: AgentRun, cutoff: datetime) -> bool:
    """Flip a too-old ``running`` row to ``failed`` in place (ORM). Returns True if it changed.

    Caller commits. Uses the ORM assignment (not a Core bulk ``UPDATE``) so ``updated_at`` bumps via
    the mixin ``onupdate`` and the swept instance is fresh for serialization — no expire/refetch.
    """
    if agent_run.status is AgentRunStatus.RUNNING and agent_run.updated_at < cutoff:
        agent_run.reserved_amount = None
        agent_run.status = AgentRunStatus.FAILED
        agent_run.error = "lost — the background worker did not finish (stale run swept on read)"
        return True
    return False


async def list_thread_agent_runs(
    db: AsyncSession, project_id: UUID, thread_id: UUID
) -> list[AgentRun]:
    """Newest-first traces for a thread, sweeping any stale ``running`` rows to ``failed`` first."""
    rows = list(
        (
            await db.execute(
                select(AgentRun)
                .where(AgentRun.project_id == project_id, AgentRun.thread_id == thread_id)
                .order_by(AgentRun.created_at.desc())
            )
        ).scalars()
    )
    cutoff = _stale_running_cutoff()
    # Evaluate the whole list *before* the ``any`` — a generator would short-circuit and leave later
    # stale rows unswept.
    swept = [_sweep_if_stale(row, cutoff) for row in rows]
    if any(swept):
        await db.commit()
    return rows


async def get_agent_run(db: AsyncSession, agent_run_id: UUID) -> AgentRun:
    """The poll target: one full trace (``404`` if unknown), sweeping it if it is a stale run."""
    agent_run = await db.get(AgentRun, agent_run_id)
    if agent_run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent run not found")
    if _sweep_if_stale(agent_run, _stale_running_cutoff()):
        await db.commit()
    return agent_run
