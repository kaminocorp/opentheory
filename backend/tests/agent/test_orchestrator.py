"""The bounded orchestrator (0.12.2) — DB-backed (skips without ``TEST_DATABASE_URL``).

Drives ``run_agent_pass`` with a **stub planner** (a canned ``PlanResult`` — no LLM) so the
orchestration logic is deterministic, while ``run_instrument`` and the checkpoint chokepoint run for
real. Covers the plan's Phase 3 matrix: the flagship happy path (attributed checkpoint + evidence on
the agent branch), the failure split, the safety cap (via the real planner + a ``StubLlm``), branch
reuse vs. re-fork after close, the main-line fallback, an unassigned role, and a planner failure.
"""

import json
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
from app.models.enums import ActorType, AgentRunStatus, BranchStatus
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
    resp = await client.post("/api/v1/actors", json={"type": "human", "display_name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _project(client: AsyncClient, slug: str) -> str:
    author = await client.post("/api/v1/actors", json={"type": "human", "display_name": "Author"})
    assert author.status_code == 201, author.text
    resp = await client.post(
        "/api/v1/projects",
        json={"title": "Agent", "slug": slug, "question": "What is X?"},
        headers={"X-Dev-Actor-Id": author.json()["id"]},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


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


async def _assign_model(
    session_factory: async_sessionmaker, project_id: str, role: str = "researcher"
) -> None:
    async with session_factory() as session:
        project = await session.get(Project, UUID(project_id))
        project.agent_models = {role: "anthropic/claude-sonnet-4"}
        await session.commit()


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


def _stub_planner(plan_result: PlanResult):
    async def _planner(thread, open_claims, catalog, model, *, llm, max_runs):
        return plan_result

    return _planner


def _raising_planner(exc: Exception):
    async def _planner(thread, open_claims, catalog, model, *, llm, max_runs):
        raise exc

    return _planner


# --- tests ---------------------------------------------------------------------------------------


async def test_pass_lands_attributed_checkpoint_and_evidence_on_the_agent_branch(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client, "agent-happy")
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
        landed = result.steps[-1]
        assert landed["status"] == "landed"
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


async def test_failure_split_one_bad_step_does_not_abort_the_pass(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client, "agent-failsplit")
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
    project_id = await _project(client, "agent-cap")
    thread_id = await _thread(client, project_id, actor_id)
    await _thread_checkpoint(client, project_id, thread_id, actor_id)
    await _assign_model(session_factory, project_id)
    run_id = await _make_run(session_factory, project_id, thread_id, actor_id)

    monkeypatch.setattr(settings, "agent_pass_max_runs", 3)
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
    project_id = await _project(client, "agent-reuse")
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
    project_id = await _project(client, "agent-fallback")
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
        checkpoint_id = UUID(result.steps[-1]["checkpoint_id"])

    async with session_factory() as session:
        checkpoint = await session.get(Checkpoint, checkpoint_id)
        assert checkpoint.branch_id is None  # landed on the main line


async def test_unassigned_role_fails_and_mints_nothing(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client, "agent-norole")
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
    project_id = await _project(client, "agent-plannerfail")
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
