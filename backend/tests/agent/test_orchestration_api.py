"""The orchestration API surface (0.22.0) — commission, poll, and the gate edges.

DB-free gates run in the default suite (they reject before any DB access):

- **dark launch** — with ``agent_loop_enabled`` off, an unauthenticated ``POST`` is
  ``404`` (not ``401``);
- **auth** — with the flag on, an unauthenticated ``POST`` is ``401``.

The rest is DB-backed (skips without ``TEST_DATABASE_URL``).
"""

import asyncio
from decimal import Decimal
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agent.planner import PlannedRun, PlanResult
from app.core.config import settings
from app.models.enums import FundingKind, FundingSource, FundingStatus
from app.models.funding import FundingAllocation
from app.models.project import Project
from app.services import orchestration as orchestration_service
from app.services.orchestration import OrchestrationExecutor

_BOGUS = "00000000-0000-0000-0000-000000000000"


def test_dark_launch_post_is_404_when_disabled(dbfree_client: TestClient) -> None:
    resp = dbfree_client.post(
        f"/api/v1/projects/{_BOGUS}/orchestrations",
        json={"role": "researcher"},
    )
    assert resp.status_code == 404, resp.text


def test_dark_launch_get_is_404_when_disabled(dbfree_client: TestClient) -> None:
    resp = dbfree_client.get(f"/api/v1/orchestrations/{_BOGUS}")
    assert resp.status_code == 404, resp.text


def test_dark_launch_cancel_is_404_when_disabled(dbfree_client: TestClient) -> None:
    resp = dbfree_client.post(f"/api/v1/orchestrations/{_BOGUS}/cancel")
    assert resp.status_code == 404, resp.text


def test_unauthenticated_post_is_401_when_enabled(
    dbfree_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "agent_loop_enabled", True)
    monkeypatch.setattr(settings, "auth_dev_header_enabled", False)
    resp = dbfree_client.post(
        f"/api/v1/projects/{_BOGUS}/orchestrations",
        json={"role": "researcher"},
    )
    assert resp.status_code == 401, resp.text


async def _project_owned_by(client: AsyncClient, actor_id: str, slug: str) -> str:
    resp = await client.post(
        "/api/v1/projects",
        json={"title": "Orch", "slug": slug, "question": "What is X?"},
        headers={"X-Dev-Actor-Id": actor_id},
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


async def _claim(client: AsyncClient, thread_id: str, actor_id: str) -> None:
    resp = await client.post(
        f"/api/v1/threads/{thread_id}/claims",
        json={"kind": "hypothesis", "statement": "A raisable claim."},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert resp.status_code == 201, resp.text


async def _thread_checkpoint(
    client: AsyncClient, project_id: str, thread_id: str, actor_id: str
) -> None:
    resp = await client.post(
        f"/api/v1/projects/{project_id}/checkpoints",
        json={"summary": "seed", "thread_id": thread_id},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert resp.status_code == 201, resp.text


async def _assign_model(session_factory: async_sessionmaker, project_id: str) -> None:
    async with session_factory() as session:
        project = await session.get(Project, UUID(project_id))
        project.agent_models = {"researcher": "anthropic/claude-sonnet-4"}
        session.add(
            FundingAllocation(
                project_id=UUID(project_id),
                amount=Decimal("100.00"),
                currency="USD",
                kind=FundingKind.TOP_UP,
                source=FundingSource.NATIVE,
                status=FundingStatus.SETTLED,
            )
        )
        await session.commit()


def _stub_planner(plan_result: PlanResult):
    calls = {"n": 0}

    async def _planner(
        thread, open_claims, catalog, model, *, llm, max_runs, grounding=None, observations=None
    ):
        calls["n"] += 1
        if calls["n"] == 1:
            return plan_result
        return PlanResult(runnable=[], proposed_count=0, tokens_used=0)

    return _planner


async def _poll_until_terminal(client: AsyncClient, run_id: str, tries: int = 60) -> dict:
    for _ in range(tries):
        resp = await client.get(f"/api/v1/orchestrations/{run_id}")
        assert resp.status_code == 200, resp.text
        if resp.json()["status"] in ("completed", "failed"):
            return resp.json()
        await asyncio.sleep(0.05)
    raise AssertionError("orchestration did not reach a terminal state")


async def test_non_member_is_403(
    client: AsyncClient, internal_funder, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "agent_loop_enabled", True)
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await _project_owned_by(client, owner_id, "orch-403")
    outsider_id, _ = await internal_funder(client, roles=(), display_name="Outsider")

    resp = await client.post(
        f"/api/v1/projects/{project_id}/orchestrations",
        json={"role": "researcher"},
        headers={"X-Dev-Actor-Id": outsider_id},
    )
    assert resp.status_code == 403, resp.text


async def test_bad_role_is_422(
    client: AsyncClient, internal_funder, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "agent_loop_enabled", True)
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await _project_owned_by(client, owner_id, "orch-422")

    resp = await client.post(
        f"/api/v1/projects/{project_id}/orchestrations",
        json={"role": "wizard"},
        headers={"X-Dev-Actor-Id": owner_id},
    )
    assert resp.status_code == 422, resp.text


async def test_full_round_trip_commissions_and_polls(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    internal_funder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "agent_loop_enabled", True)
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await _project_owned_by(client, owner_id, "orch-roundtrip")
    thread_id = await _thread(client, project_id, owner_id)
    await _claim(client, thread_id, owner_id)
    await _thread_checkpoint(client, project_id, thread_id, owner_id)
    await _assign_model(session_factory, project_id)

    plan_result = PlanResult(
        runnable=[
            PlannedRun(instrument="calc.eval", inputs={"expression": "1 + 1 == 2"}, rationale="ok")
        ],
        dropped=[],
        tokens_used=17,
        proposed_count=1,
    )
    monkeypatch.setattr(
        orchestration_service,
        "background_executor",
        OrchestrationExecutor(session_factory=session_factory, planner=_stub_planner(plan_result)),
    )

    resp = await client.post(
        f"/api/v1/projects/{project_id}/orchestrations",
        json={"role": "researcher"},
        headers={"X-Dev-Actor-Id": owner_id},
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["status"] == "running"
    assert body["role"] == "researcher"
    run_id = body["id"]

    trace = await _poll_until_terminal(client, run_id)
    assert trace["status"] == "completed"
    assert trace["stop_reason"] == "no_open_work"
    assert trace["passes_commissioned"] == 1
    assert trace["passes_completed"] == 1
    assert trace["decisions"][0]["thread_id"] == thread_id
    assert trace["decisions"][0]["action"] == "commissioned"
    assert trace["decisions"][0]["agent_run_id"]

    listing = await client.get(f"/api/v1/projects/{project_id}/orchestrations")
    assert listing.status_code == 200, listing.text
    listed = next(r for r in listing.json() if r["id"] == run_id)
    assert listed["status"] == "completed"
    assert listed["passes_commissioned"] == 1


async def test_second_in_flight_orchestration_is_409(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    internal_funder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two overlapping loops on the same project would race the shared pot."""
    monkeypatch.setattr(settings, "agent_loop_enabled", True)
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await _project_owned_by(client, owner_id, "orch-409")

    from app.models.actor import Actor
    from app.models.enums import OrchestrationRunStatus
    from app.models.orchestration_run import OrchestrationRun

    async with session_factory() as session:
        actor = await session.get(Actor, UUID(owner_id))
        session.add(
            OrchestrationRun(
                project_id=UUID(project_id),
                triggered_by_actor_id=actor.id,
                role="researcher",
                status=OrchestrationRunStatus.RUNNING,
                max_passes=4,
            )
        )
        await session.commit()

    resp = await client.post(
        f"/api/v1/projects/{project_id}/orchestrations",
        json={"role": "researcher"},
        headers={"X-Dev-Actor-Id": owner_id},
    )
    assert resp.status_code == 409, resp.text
