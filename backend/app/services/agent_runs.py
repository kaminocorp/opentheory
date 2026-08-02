"""The bounded agent orchestrator (0.12.2) — one pass, executed on an agent branch, fully traced.

``run_agent_pass`` is the thin loop's engine. It composes the reuse spine and invents **no** ledger
mechanics: it resolves the project's agent Actor, calls the planner **once**, selects (or forks) the
thread's agent branch *only when a run will actually land*, then executes each runnable step through
the **same** ``run_instrument`` chokepoint humans use — attributed to the agent Actor, on the agent
branch. Every step is recorded on the ``AgentRun`` trace; a per-step failure is caught so one bad
run never aborts the pass. Forking after planning keeps a failed or empty pass free of any mint.

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
from typing import Any, Protocol
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.llm import AgentLlmError, LlmClient, OpenRouterClient
from app.agent.planner import PlanResult
from app.agent.planner import plan as default_plan
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.actor import Actor
from app.models.agent_run import AgentRun
from app.models.branch import Branch
from app.models.claim import Claim
from app.models.enums import AgentRunStatus, BranchStatus, ClaimStatus
from app.models.project import Project
from app.models.thread import Thread
from app.schemas.branch import BranchCreate
from app.services import branches as branch_service
from app.services import checkpoints as checkpoint_service
from app.services.agent_actors import get_or_create_project_agent_actor
from app.services.grounding import compute_yield, grounding_by_claim
from app.services.tool_runs import run_instrument
from app.toolbench.catalog import build_catalog
from app.toolbench.registry import registry

logger = logging.getLogger(__name__)

# Claim statuses that are "settled" — the planner is not offered these (a retracted claim is
# withdrawn; a validated one is done). Everything else on the thread is an open claim.
_SETTLED_CLAIM_STATUSES = (ClaimStatus.RETRACTED, ClaimStatus.VALIDATED)

# The planner is injectable (a canned callable in tests). Its shape mirrors ``agent.planner.plan``.
PlannerFn = Callable[..., Awaitable[PlanResult]]


class BudgetPolicy(Protocol):
    """The budget seam (Decision #4). ``check`` returns ``True`` to keep going.

    v1 passes ``None`` here — the per-pass safety caps (``agent_pass_max_runs``) already bound blast
    radius, and real budget is a **project-level** concern (0.12.5). A future orchestrator agent
    supplies a project-budget-derived policy through this seam; **no per-thread limits ever**.

    Deliberately unchanged in 0.16.1: the signature has no implementer yet, so widening it now would
    be speculative. What that release *does* supply is the missing half of metering — the recorded
    ``AgentRun.grounding_yield``, which is what lets a budget ask "what did the last pass buy?"
    instead of only "how much did it spend?".
    """

    def check(self, *, tokens_used: int, ran_count: int) -> bool: ...


async def _open_claims(db: AsyncSession, thread_id: UUID) -> list[Claim]:
    """The thread's claims that are still in play (not retracted/validated), oldest first."""
    result = await db.execute(
        select(Claim)
        .where(
            Claim.thread_id == thread_id,
            Claim.status.notin_(_SETTLED_CLAIM_STATUSES),
        )
        .order_by(Claim.created_at)
    )
    return list(result.scalars())


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


def _executed_step(index: int, run: Any, *, status: str, **extra: Any) -> dict[str, Any]:
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
    }


async def _finalize(
    db: AsyncSession,
    agent_run: AgentRun,
    *,
    status: AgentRunStatus,
    error: str | None = None,
) -> AgentRun:
    """Commit the current (maybe partial) trace with a terminal status. Never leaves ``running``."""
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

    # 3. The ONE planning call — BEFORE any branch fork, so a planner failure (down provider /
    #    unparseable plan) is a recorded failed trace that mints nothing at all.
    #
    #    The grounding snapshot (0.16.1) is loaded once, here, and serves *both* consumers: it is
    #    the planner's context (plan to raise a rung) and the ``before`` half of the yield measure.
    #    One batched query, not two — and taking it before the plan means the state the model
    #    reasoned about is exactly the state the yield is measured against.
    open_claims = await _open_claims(db, agent_run.thread_id)
    claim_ids = [claim.id for claim in open_claims]
    grounding_before = await grounding_by_claim(db, claim_ids)
    the_llm: LlmClient = llm if llm is not None else OpenRouterClient()
    try:
        plan_result = await planner(
            thread,
            open_claims,
            build_catalog(),
            model,
            llm=the_llm,
            max_runs=settings.agent_pass_max_runs,
            grounding=grounding_before,
        )
    except AgentLlmError as exc:
        agent_run.tokens_used = getattr(exc, "tokens_used", 0)
        return await _finalize(
            db, agent_run, status=AgentRunStatus.FAILED, error=f"planner failed: {exc}"
        )

    # Persist the plan + dropped steps + usage before executing, so a poll mid-pass sees the plan.
    steps: list[dict[str, Any]] = list(plan_result.dropped)
    agent_run.plan = {"runs": [run.model_dump(mode="json") for run in plan_result.runnable]}
    agent_run.planned_count = plan_result.proposed_count
    agent_run.tokens_used = plan_result.tokens_used
    agent_run.steps = list(steps)
    await db.commit()

    # 4. Select the agent branch (reuse / fork / main-line fallback) — but ONLY now that we know a
    #    run will actually land. Forking mints a branch-creation checkpoint, so an empty plan (0
    #    runnable) or a planner failure never creates a stray branch. Reuse across passes is a query
    #    (mints nothing) and still resolves the durable agent line.
    branch_id: UUID | None = None
    if plan_result.runnable:
        branch_id = await select_agent_branch(
            db, agent_run.project_id, agent_run.thread_id, agent_actor, role=agent_run.role
        )
        agent_run.branch_id = branch_id
        await db.commit()

    # 5. Execute the runnable steps (already ≤ agent_pass_max_runs). Each landed run is its own
    #    atomic transaction; a per-step failure is caught and recorded (mints nothing).
    ran_count = 0
    for index, run in enumerate(plan_result.runnable):
        if budget_policy is not None and not budget_policy.check(
            tokens_used=agent_run.tokens_used, ran_count=ran_count
        ):
            steps.append(_executed_step(index, run, status="skipped", reason="budget_exhausted"))
            agent_run.steps = list(steps)
            await db.commit()
            break

        instrument = registry.get(run.instrument)
        if instrument is None:  # pragma: no cover - the planner already resolved it
            steps.append(_executed_step(index, run, status="failed", error="instrument not found"))
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
            steps.append(_executed_step(index, run, status="failed", error=str(exc.detail)))
            agent_run.steps = list(steps)
            await db.commit()
            continue

        ran_count += 1
        steps.append(
            _executed_step(
                index,
                run,
                status="landed",
                checkpoint_id=str(result.checkpoint.id),
                evidence_id=str(result.evidence_id) if result.evidence_id is not None else None,
                outcome=result.status.value,
            )
        )
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

    agent_run.ran_count = ran_count
    agent_run.steps = list(steps)

    # 6. Measure the yield (0.16.1): re-read grounding for the same claims and diff it against the
    #    pre-plan snapshot. Every landed step has already committed, so this reads the pass's own
    #    durable effect. It is deliberately measured for *every* completed pass, including one that
    #    ran nothing — "measured 4, moved 0" is the honest record of a pass that bought nothing, and
    #    it is the number 0.12.5's metering will read (see BudgetPolicy).
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
) -> AgentRun:
    """Mint the ``running`` trace row in the **request** session and commit it (the ``POST`` half).

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
    await db.commit()
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

    Worst-case wall-clock for a legitimate pass = the single planning call (``agent_llm_timeout_s``)
    + up to ``agent_pass_max_runs`` instrument runs (each bounded by ``toolbench_wall_timeout_s``) +
    a margin. Anything ``running`` and untouched for longer than that had its worker die.
    """
    ttl = (
        settings.agent_llm_timeout_s
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
