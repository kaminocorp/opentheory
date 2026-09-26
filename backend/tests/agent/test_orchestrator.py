"""The bounded orchestrator (0.12.2) — DB-backed (skips without ``TEST_DATABASE_URL``).

Drives ``run_agent_pass`` with a **stub planner** (a canned ``PlanResult`` — no LLM) so the
orchestration logic is deterministic, while ``run_instrument`` and the checkpoint chokepoint run for
real. Covers the plan's Phase 3 matrix: the flagship happy path (attributed checkpoint + evidence on
the agent branch), the failure split, the safety cap (via the real planner + a ``StubLlm``), branch
reuse vs. re-fork after close, the main-line fallback, an unassigned role, and a planner failure.
"""

import json
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agent.llm import AgentLlmError
from app.agent.planner import PlannedRun, PlanResult
from app.core.config import settings
from app.models.actor import Actor
from app.models.agent_run import AgentRun
from app.models.branch import Branch
from app.models.checkpoint import Checkpoint
from app.models.contribution import Contribution
from app.models.enums import (
    ActorType,
    AgentRunStatus,
    BranchStatus,
    FundingKind,
    FundingSource,
    FundingStatus,
)
from app.models.funding import FundingAllocation
from app.models.project import Project
from app.schemas.branch import BranchClose
from app.services import branches as branch_service
from app.services.agent_runs import run_agent_pass
from tests.agent.stubs import StubLlm

# Refutes: 3 + 4 ≠ 5 in the stated integer box (mirrors test_instruments_write_path.py).
_GEOMETRY_STORY_SEARCH = {
    "relation": "d == a + b",
    "variables": {"a": {"min": 3, "max": 3}, "b": {"min": 4, "max": 4}, "d": {"min": 5, "max": 5}},
}


# --- HTTP + session setup helpers ----------------------------------------------------------------


async def _actor(client: AsyncClient, name: str = "Ada") -> str:
    from tests.principals import make_dev_principal

    return await make_dev_principal(client, display_name=name)


async def _project(
    client: AsyncClient, slug: str = "test-project", actor_id: str | None = None
) -> str:
    from tests.principals import create_owned_project, make_dev_principal

    if actor_id is None:
        actor_id = await make_dev_principal(client, display_name="Author")
    return await create_owned_project(client, actor_id, slug)


async def _thread(client: AsyncClient, project_id: str, actor_id: str) -> str:
    resp = await client.post(
        f"/api/v1/projects/{project_id}/threads",
        json={"title": "T", "question": "q?"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _claim(client: AsyncClient, thread_id: str, actor_id: str, statement: str) -> str:
    resp = await client.post(
        f"/api/v1/threads/{thread_id}/claims",
        json={"kind": "hypothesis", "statement": statement},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _thread_checkpoint(
    client: AsyncClient, project_id: str, thread_id: str, actor_id: str
) -> str:
    """A main-line checkpoint on the thread — the fork point an agent branch needs."""
    resp = await client.post(
        f"/api/v1/projects/{project_id}/checkpoints",
        json={"summary": "seed", "thread_id": thread_id},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _grant_budget(
    session_factory: async_sessionmaker, project_id: str, *, amount: str = "100.00"
) -> None:
    """Settled native funding so the 0.19.0 project ceiling lets a pass start."""
    async with session_factory() as session:
        session.add(
            FundingAllocation(
                project_id=UUID(project_id),
                amount=Decimal(amount),
                currency="USD",
                kind=FundingKind.TOP_UP,
                source=FundingSource.NATIVE,
                status=FundingStatus.SETTLED,
            )
        )
        await session.commit()


async def _assign_model(
    session_factory: async_sessionmaker,
    project_id: str,
    role: str = "researcher",
    *,
    budget: str | None = "100.00",
) -> None:
    async with session_factory() as session:
        project = await session.get(Project, UUID(project_id))
        project.agent_models = {role: "anthropic/claude-sonnet-4"}
        await session.commit()
    if budget is not None:
        await _grant_budget(session_factory, project_id, amount=budget)


async def _make_run(
    session_factory: async_sessionmaker,
    project_id: str,
    thread_id: str,
    actor_id: str,
    role: str = "researcher",
) -> UUID:
    """Create the ``AgentRun(running)`` row the way the 0.12.3 route will, and return its id."""
    async with session_factory() as session:
        agent_run = AgentRun(
            project_id=UUID(project_id),
            thread_id=UUID(thread_id),
            triggered_by_actor_id=UUID(actor_id),
            role=role,
            status=AgentRunStatus.RUNNING,
        )
        session.add(agent_run)
        await session.commit()
        return agent_run.id


# The stub planners mirror ``agent.planner.plan``'s signature *explicitly* — including 0.16.1's
# ``grounding`` and 0.20.0's ``observations`` — rather than swallowing extras with ``**kwargs``.
# That is deliberate: the planner is an injected seam, so a stub that quietly accepts anything
# would let the orchestrator start passing an argument the real planner never receives, and no
# test would notice.
#
# A one-shot stub returns ``plan_result`` on the first call and an empty plan afterwards, so
# existing tests keep a single batch. Replan tests pass ``then=[...]``.


def _stub_planner(
    plan_result: PlanResult,
    *,
    seen: dict | None = None,
    then: list[PlanResult] | None = None,
):
    calls = {"n": 0}

    async def _planner(
        thread, open_claims, catalog, model, *, llm, max_runs, grounding=None, observations=None
    ):
        calls["n"] += 1
        if seen is not None:
            seen.setdefault("calls", []).append(
                {"grounding": grounding, "observations": observations, "max_runs": max_runs}
            )
            # First-call grounding is the yield's ``before`` — keep that contract for 0.16.1 tests.
            if "grounding" not in seen:
                seen["grounding"] = grounding
            seen["observations"] = observations
        if calls["n"] == 1:
            return plan_result
        if then is not None:
            idx = calls["n"] - 2
            if 0 <= idx < len(then):
                return then[idx]
        return PlanResult(runnable=[], proposed_count=0, tokens_used=0)

    return _planner


def _raising_planner(exc: Exception):
    async def _planner(
        thread, open_claims, catalog, model, *, llm, max_runs, grounding=None, observations=None
    ):
        raise exc

    return _planner


def _always_planner(plan_result: PlanResult, *, seen: dict | None = None):
    """A stub that keeps proposing the same batch — used to prove the max-replan stop."""

    async def _planner(
        thread, open_claims, catalog, model, *, llm, max_runs, grounding=None, observations=None
    ):
        if seen is not None:
            seen.setdefault("n", 0)
            seen["n"] += 1
            seen["observations"] = observations
        return plan_result

    return _planner


# --- tests ---------------------------------------------------------------------------------------


async def test_pass_lands_attributed_checkpoint_and_evidence_on_the_agent_branch(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client, "agent-happy", actor_id=actor_id)
    thread_id = await _thread(client, project_id, actor_id)
    claim_id = await _claim(client, thread_id, actor_id, "Return distance equals the sum of legs.")
    await _thread_checkpoint(client, project_id, thread_id, actor_id)  # fork point
    await _assign_model(session_factory, project_id)
    run_id = await _make_run(session_factory, project_id, thread_id, actor_id)

    plan_result = PlanResult(
        runnable=[
            PlannedRun(
                instrument="counterexample.search",
                inputs=_GEOMETRY_STORY_SEARCH,
                claim_id=UUID(claim_id),
                relation_kind="weaken",
                rationale="hunt for a counterexample",
            )
        ],
        dropped=[],
        tokens_used=42,
        proposed_count=1,
    )

    async with session_factory() as session:
        result = await run_agent_pass(session, run_id, planner=_stub_planner(plan_result))
        assert result.status is AgentRunStatus.COMPLETED
        assert result.ran_count == 1
        assert result.tokens_used == 42
        assert result.branch_id is not None
        branch_id = result.branch_id
        agent_actor_id = result.agent_actor_id
        landed = next(s for s in result.steps if s["status"] == "landed")
        assert landed["outcome"] == "refuted"
        assert landed["evidence_id"] is not None
        checkpoint_id = UUID(landed["checkpoint_id"])

    async with session_factory() as session:
        agent_actor = await session.get(Actor, agent_actor_id)
        assert agent_actor.type is ActorType.AGENT
        assert agent_actor.display_name == "Research crew"

        checkpoint = await session.get(Checkpoint, checkpoint_id)
        assert checkpoint.branch_id == branch_id  # landed on the agent line
        assert checkpoint.author_id == agent_actor_id  # attributed to the agent Actor

        branch = await session.get(Branch, branch_id)
        assert branch.status is BranchStatus.OPEN

        contrib = (
            await session.execute(
                select(Contribution).where(Contribution.checkpoint_id == checkpoint_id)
            )
        ).scalar_one()
        assert contrib.action == "tool_run"


# --- 0.16.1: the yield measure, end to end --------------------------------------------------------


async def test_pass_records_the_rung_it_moved(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    """Acceptance 5/6 through the real chokepoint: an exact witness settles the claim.

    Also pins the *input* half — the pre-plan grounding snapshot is what the planner actually
    receives, so the state the model reasons about is the state the yield is measured against.
    """
    actor_id = await _actor(client)
    project_id = await _project(client, "agent-yield", actor_id=actor_id)
    thread_id = await _thread(client, project_id, actor_id)
    claim_id = await _claim(client, thread_id, actor_id, "Return distance equals the sum of legs.")
    await _thread_checkpoint(client, project_id, thread_id, actor_id)
    await _assign_model(session_factory, project_id)
    run_id = await _make_run(session_factory, project_id, thread_id, actor_id)

    seen: dict = {}
    plan_result = PlanResult(
        runnable=[
            PlannedRun(
                instrument="counterexample.search",
                inputs=_GEOMETRY_STORY_SEARCH,
                claim_id=UUID(claim_id),
                relation_kind="weaken",
                rationale="hunt for a counterexample",
            )
        ],
        tokens_used=1,
        proposed_count=1,
    )

    async with session_factory() as session:
        result = await run_agent_pass(
            session, run_id, planner=_stub_planner(plan_result, seen=seen)
        )

    # The planner saw the claim's *pre-pass* state: no evidence links at all, so the claim is
    # absent from the batch-loaded map — which the prompt renders as ``ungrounded``. Asserted as an
    # equality rather than a disjunction: an ``or`` here would pass on either reading and so could
    # not tell a correct empty snapshot from a snapshot that was never taken.
    assert seen["grounding"] == {}

    measure = result.grounding_yield
    assert measure["measured"] == 1
    assert measure["moved"] == 1
    moved = measure["changed"][0]
    assert moved["claim_id"] == claim_id
    assert (moved["before"], moved["after"], moved["movement"]) == (
        "ungrounded",
        "refuted",
        "settled",
    )


async def test_a_pass_that_mints_a_checkpoint_but_moves_no_rung_says_so(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    """Acceptance 4 + 7 — the case the release exists for.

    The run lands a real, attributed checkpoint but targets no claim, so no evidence links to the
    ladder and nothing climbs. Activity without yield must be visible as exactly that: a non-zero
    ``ran_count`` beside ``moved: 0``.
    """
    actor_id = await _actor(client)
    project_id = await _project(client, "agent-noyield", actor_id=actor_id)
    thread_id = await _thread(client, project_id, actor_id)
    await _claim(client, thread_id, actor_id, "Some untouched open claim.")
    await _thread_checkpoint(client, project_id, thread_id, actor_id)
    await _assign_model(session_factory, project_id)
    run_id = await _make_run(session_factory, project_id, thread_id, actor_id)

    plan_result = PlanResult(
        runnable=[
            PlannedRun(
                instrument="calc.eval",
                inputs={"expression": "1 + 1"},
                rationale="compute something unrelated",
            )
        ],
        tokens_used=1,
        proposed_count=1,
    )

    async with session_factory() as session:
        result = await run_agent_pass(session, run_id, planner=_stub_planner(plan_result))

    assert result.status is AgentRunStatus.COMPLETED
    assert result.ran_count == 1  # it did mint a checkpoint
    assert result.grounding_yield["measured"] == 1
    assert result.grounding_yield["moved"] == 0  # …and bought nothing
    assert result.grounding_yield["changed"] == []


async def test_failure_split_one_bad_step_does_not_abort_the_pass(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client, "agent-failsplit", actor_id=actor_id)
    thread_id = await _thread(client, project_id, actor_id)
    await _thread_checkpoint(client, project_id, thread_id, actor_id)
    await _assign_model(session_factory, project_id)
    run_id = await _make_run(session_factory, project_id, thread_id, actor_id)

    plan_result = PlanResult(
        runnable=[
            # Step 1 lands (a true relation).
            PlannedRun(instrument="calc.eval", inputs={"expression": "1 + 1 == 2"}, rationale="ok"),
            # Step 2 targets a non-existent claim → run_instrument raises 404 *before* any db.add.
            PlannedRun(
                instrument="calc.eval",
                inputs={"expression": "2 + 2 == 4"},
                claim_id=uuid4(),
                rationale="doomed",
            ),
        ],
        proposed_count=2,
    )

    async with session_factory() as session:
        result = await run_agent_pass(session, run_id, planner=_stub_planner(plan_result))
        assert result.status is AgentRunStatus.COMPLETED  # the pass still completes
        assert result.ran_count == 1
        executed = [s for s in result.steps if s["status"] in ("landed", "failed")]
        assert [s["status"] for s in executed] == ["landed", "failed"]
        assert executed[1]["checkpoint_id"] is None  # the failed step minted nothing
        assert executed[1]["error"]

    async with session_factory() as session:
        # Exactly one tool_run landed — the failed step left no orphan checkpoint.
        tool_runs = (
            await session.execute(
                select(Contribution).where(Contribution.action == "tool_run")
            )
        ).scalars().all()
        assert len(tool_runs) == 1


async def test_safety_cap_truncates_to_max_runs(
    client: AsyncClient, session_factory: async_sessionmaker, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client, "agent-cap", actor_id=actor_id)
    thread_id = await _thread(client, project_id, actor_id)
    await _thread_checkpoint(client, project_id, thread_id, actor_id)
    await _assign_model(session_factory, project_id)
    run_id = await _make_run(session_factory, project_id, thread_id, actor_id)

    monkeypatch.setattr(settings, "agent_pass_max_runs", 3)
    monkeypatch.setattr(settings, "agent_pass_max_replans", 0)  # isolate the planner cap
    # The REAL planner + a StubLlm proposing 10 valid runs → truncated to 3 by the cap.
    runs = [{"instrument": "calc.eval", "inputs": {"expression": f"{i} == {i}"}} for i in range(10)]
    ten = json.dumps({"runs": runs})

    async with session_factory() as session:
        result = await run_agent_pass(session, run_id, llm=StubLlm(ten))
        assert result.status is AgentRunStatus.COMPLETED
        assert result.ran_count == 3
        assert result.planned_count == 10
        landed = [s for s in result.steps if s["status"] == "landed"]
        capped = [s for s in result.steps if s.get("reason") == "max_runs"]
        assert len(landed) == 3
        assert len(capped) == 7


async def test_branch_is_reused_across_passes_then_reforked_after_close(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client, "agent-reuse", actor_id=actor_id)
    thread_id = await _thread(client, project_id, actor_id)
    await _thread_checkpoint(client, project_id, thread_id, actor_id)
    await _assign_model(session_factory, project_id)

    def one_run() -> PlanResult:
        return PlanResult(
            runnable=[PlannedRun(instrument="calc.eval", inputs={"expression": "1 == 1"})],
            proposed_count=1,
        )

    run1 = await _make_run(session_factory, project_id, thread_id, actor_id)
    async with session_factory() as session:
        r1 = await run_agent_pass(session, run1, planner=_stub_planner(one_run()))
        branch_a = r1.branch_id
    assert branch_a is not None

    run2 = await _make_run(session_factory, project_id, thread_id, actor_id)
    async with session_factory() as session:
        r2 = await run_agent_pass(session, run2, planner=_stub_planner(one_run()))
        assert r2.branch_id == branch_a  # reused the same open agent line

    # Close the agent line, then a third pass must fork a NEW branch.
    async with session_factory() as session:
        actor = await session.get(Actor, UUID(actor_id))
        await branch_service.close_branch(
            session, branch_a, BranchClose(outcome="dead_end", reason="done"), actor
        )

    run3 = await _make_run(session_factory, project_id, thread_id, actor_id)
    async with session_factory() as session:
        r3 = await run_agent_pass(session, run3, planner=_stub_planner(one_run()))
        assert r3.branch_id is not None
        assert r3.branch_id != branch_a  # a fresh line, not the closed one


async def test_main_line_fallback_when_thread_has_no_checkpoint(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client, "agent-fallback", actor_id=actor_id)
    thread_id = await _thread(client, project_id, actor_id)
    await _assign_model(session_factory, project_id)  # NOTE: no checkpoint on the thread
    run_id = await _make_run(session_factory, project_id, thread_id, actor_id)

    plan_result = PlanResult(
        runnable=[PlannedRun(instrument="calc.eval", inputs={"expression": "1 == 1"})],
        proposed_count=1,
    )

    async with session_factory() as session:
        result = await run_agent_pass(session, run_id, planner=_stub_planner(plan_result))
        assert result.status is AgentRunStatus.COMPLETED
        assert result.ran_count == 1
        assert result.branch_id is None  # the documented fallback
        landed = next(s for s in result.steps if s["status"] == "landed")
        checkpoint_id = UUID(landed["checkpoint_id"])

    async with session_factory() as session:
        checkpoint = await session.get(Checkpoint, checkpoint_id)
        assert checkpoint.branch_id is None  # landed on the main line


async def test_unassigned_role_fails_and_mints_nothing(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client, "agent-norole", actor_id=actor_id)
    thread_id = await _thread(client, project_id, actor_id)
    # Deliberately do NOT assign a model to "researcher".
    run_id = await _make_run(session_factory, project_id, thread_id, actor_id)

    async with session_factory() as session:
        result = await run_agent_pass(
            session,
            run_id,
            planner=_raising_planner(AssertionError("planner must not be called")),
        )
        assert result.status is AgentRunStatus.FAILED
        assert "no model assigned" in result.error
        assert result.ran_count == 0

    async with session_factory() as session:
        tool_runs = (
            await session.execute(
                select(Contribution).where(Contribution.action == "tool_run")
            )
        ).scalars().all()
        assert tool_runs == []


async def test_planner_failure_is_a_recorded_failed_trace(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client, "agent-plannerfail", actor_id=actor_id)
    thread_id = await _thread(client, project_id, actor_id)
    await _thread_checkpoint(client, project_id, thread_id, actor_id)
    await _assign_model(session_factory, project_id)
    run_id = await _make_run(session_factory, project_id, thread_id, actor_id)

    async with session_factory() as session:
        result = await run_agent_pass(
            session,
            run_id,
            planner=_raising_planner(AgentLlmError("provider down", tokens_used=55)),
        )
        assert result.status is AgentRunStatus.FAILED
        assert "planner failed" in result.error
        assert result.tokens_used == 55  # spend recorded honestly
        assert result.ran_count == 0

    async with session_factory() as session:
        tool_runs = (
            await session.execute(
                select(Contribution).where(Contribution.action == "tool_run")
            )
        ).scalars().all()
        assert tool_runs == []


# --- 0.20.0: plan → observe → replan --------------------------------------------------------------


async def test_replan_after_observe_runs_the_second_batch(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    """The first batch's outcomes are what the second plan is allowed to know."""
    actor_id = await _actor(client)
    project_id = await _project(client, "agent-replan", actor_id=actor_id)
    thread_id = await _thread(client, project_id, actor_id)
    claim_id = await _claim(client, thread_id, actor_id, "1 + 1 equals 2.")
    await _thread_checkpoint(client, project_id, thread_id, actor_id)
    await _assign_model(session_factory, project_id)
    run_id = await _make_run(session_factory, project_id, thread_id, actor_id)

    first = PlanResult(
        runnable=[
            PlannedRun(instrument="calc.eval", inputs={"expression": "1 + 1 == 2"}, rationale="v0")
        ],
        tokens_used=10,
        proposed_count=1,
    )
    second = PlanResult(
        runnable=[
            PlannedRun(
                instrument="calc.eval",
                inputs={"expression": "2 + 2 == 4"},
                claim_id=UUID(claim_id),
                relation_kind="support",
                rationale="v1 after observe",
            )
        ],
        tokens_used=11,
        proposed_count=1,
    )
    seen: dict = {}

    async with session_factory() as session:
        result = await run_agent_pass(
            session, run_id, planner=_stub_planner(first, seen=seen, then=[second])
        )

    assert result.status is AgentRunStatus.COMPLETED
    assert result.ran_count == 2
    assert result.tokens_used == 21
    versions = result.plan.get("versions") or []
    assert versions[0]["reason"] == "initial"
    assert versions[1]["reason"] == "replan"
    assert versions[1]["observe_summary"]
    assert "calc.eval → result" in versions[1]["observe_summary"]
    # A later empty replan (nothing more to do) is an honest stop, not a third batch.
    assert [v["version"] for v in versions[:2]] == [0, 1]

    statuses = [s["status"] for s in result.steps]
    assert statuses.count("plan") == 1
    assert statuses.count("replan") >= 1
    assert statuses.count("landed") == 2

    # The replan call saw the first batch's observation, not an empty context.
    assert len(seen["calls"]) >= 2
    second_obs = seen["calls"][1]["observations"]
    assert second_obs
    assert second_obs[0].instrument == "calc.eval"
    assert second_obs[0].status == "landed"
    assert second_obs[0].outcome == "result"
    assert second_obs[0].minted is True


async def test_max_replans_stops_even_when_runs_remain(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client, "agent-maxreplan", actor_id=actor_id)
    thread_id = await _thread(client, project_id, actor_id)
    await _thread_checkpoint(client, project_id, thread_id, actor_id)
    await _assign_model(session_factory, project_id)
    run_id = await _make_run(session_factory, project_id, thread_id, actor_id)

    monkeypatch.setattr(settings, "agent_pass_max_runs", 5)
    monkeypatch.setattr(settings, "agent_pass_max_replans", 1)
    monkeypatch.setattr(settings, "agent_pass_max_batch_runs", 1)

    seen: dict = {}
    repeating = PlanResult(
        runnable=[PlannedRun(instrument="calc.eval", inputs={"expression": "1 == 1"})],
        tokens_used=3,
        proposed_count=1,
    )

    async with session_factory() as session:
        result = await run_agent_pass(
            session, run_id, planner=_always_planner(repeating, seen=seen)
        )

    # initial + 1 replan = 2 planning calls, 2 landed runs; remaining run budget is unused.
    assert result.status is AgentRunStatus.COMPLETED
    assert result.ran_count == 2
    assert seen["n"] == 2
    assert any(s.get("reason") == "max_replans" for s in result.steps)
    versions = result.plan.get("versions") or []
    assert [v["version"] for v in versions] == [0, 1]


async def test_settled_grounding_reaches_the_replan(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    """A claim the first batch refutes is marked settled on the next planning call."""
    actor_id = await _actor(client)
    project_id = await _project(client, "agent-replan-settled", actor_id=actor_id)
    thread_id = await _thread(client, project_id, actor_id)
    claim_id = await _claim(client, thread_id, actor_id, "Return distance equals the sum of legs.")
    await _thread_checkpoint(client, project_id, thread_id, actor_id)
    await _assign_model(session_factory, project_id)
    run_id = await _make_run(session_factory, project_id, thread_id, actor_id)

    first = PlanResult(
        runnable=[
            PlannedRun(
                instrument="counterexample.search",
                inputs=_GEOMETRY_STORY_SEARCH,
                claim_id=UUID(claim_id),
                relation_kind="weaken",
                rationale="hunt",
            )
        ],
        tokens_used=1,
        proposed_count=1,
    )
    seen: dict = {}

    async with session_factory() as session:
        result = await run_agent_pass(session, run_id, planner=_stub_planner(first, seen=seen))

    assert result.status is AgentRunStatus.COMPLETED
    assert result.ran_count == 1
    # First call saw an ungrounded claim (absent from the map). Second call must see refuted.
    assert seen["calls"][0]["grounding"] == {}
    assert len(seen["calls"]) >= 2
    replan_grounding = seen["calls"][1]["grounding"]
    assert UUID(claim_id) in replan_grounding
    assert replan_grounding[UUID(claim_id)].headline == "refuted"
    observe = seen["calls"][1]["observations"]
    assert observe[0].grounding_after == "refuted"
    assert observe[0].movement == "settled"


async def test_failed_instrument_does_not_poison_the_replan(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    """A failed first step mints nothing and the next plan can still land."""
    actor_id = await _actor(client)
    project_id = await _project(client, "agent-replan-fail", actor_id=actor_id)
    thread_id = await _thread(client, project_id, actor_id)
    await _thread_checkpoint(client, project_id, thread_id, actor_id)
    await _assign_model(session_factory, project_id)
    run_id = await _make_run(session_factory, project_id, thread_id, actor_id)

    doomed = PlanResult(
        runnable=[
            PlannedRun(
                instrument="calc.eval",
                inputs={"expression": "2 + 2 == 4"},
                claim_id=uuid4(),
                rationale="doomed",
            )
        ],
        tokens_used=4,
        proposed_count=1,
    )
    recovery = PlanResult(
        runnable=[
            PlannedRun(instrument="calc.eval", inputs={"expression": "1 == 1"}, rationale="ok")
        ],
        tokens_used=5,
        proposed_count=1,
    )
    seen: dict = {}

    async with session_factory() as session:
        result = await run_agent_pass(
            session, run_id, planner=_stub_planner(doomed, seen=seen, then=[recovery])
        )

    assert result.status is AgentRunStatus.COMPLETED
    assert result.ran_count == 1  # only the recovery landed
    executed = [s for s in result.steps if s["status"] in ("landed", "failed")]
    assert [s["status"] for s in executed] == ["failed", "landed"]
    assert executed[0]["checkpoint_id"] is None
    assert executed[1]["checkpoint_id"] is not None
    # The replan saw the failure as "minted nothing", not as a ledger outcome.
    observe = seen["calls"][1]["observations"]
    assert observe[0].status == "failed"
    assert observe[0].minted is False
    assert observe[0].outcome is None

    async with session_factory() as session:
        tool_runs = (
            await session.execute(
                select(Contribution).where(Contribution.action == "tool_run")
            )
        ).scalars().all()
        assert len(tool_runs) == 1


async def test_replan_failure_after_a_landed_step_completes_the_pass(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    """A bad replan must not invert 'one bad step never aborts the pass'."""
    actor_id = await _actor(client)
    project_id = await _project(client, "agent-replan-llmfail", actor_id=actor_id)
    thread_id = await _thread(client, project_id, actor_id)
    await _thread_checkpoint(client, project_id, thread_id, actor_id)
    await _assign_model(session_factory, project_id)
    run_id = await _make_run(session_factory, project_id, thread_id, actor_id)

    first = PlanResult(
        runnable=[PlannedRun(instrument="calc.eval", inputs={"expression": "1 == 1"})],
        tokens_used=8,
        proposed_count=1,
    )
    calls = {"n": 0}

    async def _planner(
        thread, open_claims, catalog, model, *, llm, max_runs, grounding=None, observations=None
    ):
        calls["n"] += 1
        if calls["n"] == 1:
            return first
        raise AgentLlmError("replan provider down", tokens_used=9)

    async with session_factory() as session:
        result = await run_agent_pass(session, run_id, planner=_planner)

    assert result.status is AgentRunStatus.COMPLETED
    assert result.ran_count == 1
    assert result.tokens_used == 17  # initial + failed replan spend
    replan_row = next(s for s in result.steps if s["status"] == "replan")
    assert replan_row["reason"] == "planner_failed"
    assert replan_row["observe_summary"]
