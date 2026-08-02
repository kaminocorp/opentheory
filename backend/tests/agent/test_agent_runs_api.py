"""The agent-run API surface (0.12.3) — commission, poll, and the gate edges.

Two DB-free gate tests run in the default suite (they reject before any DB access):

- **dark launch** — with ``agent_loop_enabled`` off, an *unauthenticated* ``POST`` is ``404`` (not
  ``401``), proving the router-level flag gate runs *before* ``ActingActor`` — the route is
  indistinguishable from one that does not exist yet;
- **auth** — with the flag *on*, an unauthenticated ``POST`` is ``401`` (the gate no longer masks
  the auth check).

The rest is DB-backed (skips without ``TEST_DATABASE_URL``): the member/role/scope edges (``403`` /
``422`` / ``404``), the full commission→poll→land round-trip (a stub planner injected through the
``BackgroundExecutor`` seam so the background pass runs against the test engine with no OpenRouter
key), and the unassigned-role failed trace (Decision #7: commissioned ``202``, recorded ``failed``).
"""

import asyncio
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agent.llm import AgentLlmError
from app.agent.planner import PlannedRun, PlanResult
from app.core.config import settings
from app.models.project import Project
from app.services import agent_runs as agent_run_service
from app.services.agent_runs import BackgroundExecutor

_BOGUS = "00000000-0000-0000-0000-000000000000"


# --- DB-free gates (run in the default suite) ----------------------------------------------------


def test_dark_launch_post_is_404_when_disabled(dbfree_client: TestClient) -> None:
    # Flag off (the default). An unauthenticated POST with a *valid* body is 404 — proving the
    # router-level gate runs before ActingActor (else 401) and before body validation (else 422).
    # DB-free: the 404 fires before any DB access.
    resp = dbfree_client.post(
        f"/api/v1/projects/{_BOGUS}/threads/{_BOGUS}/agent-runs",
        json={"role": "researcher"},
    )
    assert resp.status_code == 404, resp.text


def test_dark_launch_get_is_404_when_disabled(dbfree_client: TestClient) -> None:
    # The whole surface is dark: the poll target 404s too while the flag is off, before any DB read.
    resp = dbfree_client.get(f"/api/v1/agent-runs/{_BOGUS}")
    assert resp.status_code == 404, resp.text


def test_unauthenticated_post_is_401_when_enabled(
    dbfree_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # With the flag ON, the dark-launch gate passes and the auth check surfaces: no bearer token and
    # the dev-header path off → 401 from ActingActor, still before any DB access.
    monkeypatch.setattr(settings, "agent_loop_enabled", True)
    monkeypatch.setattr(settings, "auth_dev_header_enabled", False)
    resp = dbfree_client.post(
        f"/api/v1/projects/{_BOGUS}/threads/{_BOGUS}/agent-runs",
        json={"role": "researcher"},
    )
    assert resp.status_code == 401, resp.text


# --- DB-backed setup helpers (skip without TEST_DATABASE_URL) -------------------------------------


async def _project_owned_by(client: AsyncClient, actor_id: str, slug: str) -> str:
    resp = await client.post(
        "/api/v1/projects",
        json={"title": "Agent", "slug": slug, "question": "What is X?"},
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


async def _thread_checkpoint(
    client: AsyncClient, project_id: str, thread_id: str, actor_id: str
) -> None:
    """A main-line checkpoint on the thread — the fork point an agent branch needs."""
    resp = await client.post(
        f"/api/v1/projects/{project_id}/checkpoints",
        json={"summary": "seed", "thread_id": thread_id},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert resp.status_code == 201, resp.text


async def _assign_model(
    session_factory: async_sessionmaker, project_id: str, role: str = "researcher"
) -> None:
    async with session_factory() as session:
        project = await session.get(Project, UUID(project_id))
        project.agent_models = {role: "anthropic/claude-sonnet-4"}
        await session.commit()


# Signatures mirror ``agent.planner.plan`` exactly (0.16.1 added ``grounding``) — see the note in
# tests/agent/test_orchestrator.py for why these are explicit rather than ``**kwargs``.


def _stub_planner(plan_result: PlanResult):
    async def _planner(thread, open_claims, catalog, model, *, llm, max_runs, grounding=None):
        return plan_result

    return _planner


def _raising_planner(exc: Exception):
    async def _planner(thread, open_claims, catalog, model, *, llm, max_runs, grounding=None):
        raise exc

    return _planner


async def _poll_until_terminal(client: AsyncClient, run_id: str, tries: int = 60) -> dict:
    """Poll the trace like the frontend will, until it reaches ``completed``/``failed``.

    The background task normally finishes before the ``POST`` response returns under
    ``ASGITransport`` (Starlette awaits background tasks as part of the response), so this usually
    succeeds on the first read — but the loop keeps the test robust regardless of scheduling.
    """
    for _ in range(tries):
        resp = await client.get(f"/api/v1/agent-runs/{run_id}")
        assert resp.status_code == 200, resp.text
        if resp.json()["status"] in ("completed", "failed"):
            return resp.json()
        await asyncio.sleep(0.05)
    raise AssertionError("agent run did not reach a terminal state")


# --- DB-backed edges + round-trip ----------------------------------------------------------------


async def test_non_member_is_403(
    client: AsyncClient, internal_funder, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "agent_loop_enabled", True)
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await _project_owned_by(client, owner_id, "ar-403")
    thread_id = await _thread(client, project_id, owner_id)
    outsider_id, _ = await internal_funder(client, roles=(), display_name="Outsider")

    resp = await client.post(
        f"/api/v1/projects/{project_id}/threads/{thread_id}/agent-runs",
        json={"role": "researcher"},
        headers={"X-Dev-Actor-Id": outsider_id},
    )
    assert resp.status_code == 403, resp.text


async def test_bad_role_is_422(
    client: AsyncClient, internal_funder, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "agent_loop_enabled", True)
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await _project_owned_by(client, owner_id, "ar-422")
    thread_id = await _thread(client, project_id, owner_id)

    # A valid member, but 'wizard' is not one of AGENT_ROLE_FIELDS → 422 from AgentRunTrigger.
    resp = await client.post(
        f"/api/v1/projects/{project_id}/threads/{thread_id}/agent-runs",
        json={"role": "wizard"},
        headers={"X-Dev-Actor-Id": owner_id},
    )
    assert resp.status_code == 422, resp.text


async def test_thread_not_in_project_is_404(
    client: AsyncClient, internal_funder, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "agent_loop_enabled", True)
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    project_a = await _project_owned_by(client, owner_id, "ar-404a")
    project_b = await _project_owned_by(client, owner_id, "ar-404b")
    thread_b = await _thread(client, project_b, owner_id)

    # Commission on project A with project B's thread. The owner is a member of both (so membership
    # passes), but start_agent_pass rejects the cross-project thread → 404.
    resp = await client.post(
        f"/api/v1/projects/{project_a}/threads/{thread_b}/agent-runs",
        json={"role": "researcher"},
        headers={"X-Dev-Actor-Id": owner_id},
    )
    assert resp.status_code == 404, resp.text


async def test_full_round_trip_commissions_polls_and_lands(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    internal_funder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "agent_loop_enabled", True)
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await _project_owned_by(client, owner_id, "ar-roundtrip")
    thread_id = await _thread(client, project_id, owner_id)
    await _thread_checkpoint(client, project_id, thread_id, owner_id)  # fork point
    await _assign_model(session_factory, project_id)

    plan_result = PlanResult(
        runnable=[
            PlannedRun(instrument="calc.eval", inputs={"expression": "1 + 1 == 2"}, rationale="ok")
        ],
        dropped=[],
        tokens_used=17,
        proposed_count=1,
    )
    # The BackgroundTask opens its OWN session (the request session is gone), so rebind the executor
    # to the *test* engine + a stub planner — otherwise the pass would hit settings.database_url and
    # never find the row it just minted.
    monkeypatch.setattr(
        agent_run_service,
        "background_executor",
        BackgroundExecutor(session_factory=session_factory, planner=_stub_planner(plan_result)),
    )

    resp = await client.post(
        f"/api/v1/projects/{project_id}/threads/{thread_id}/agent-runs",
        json={"role": "researcher"},
        headers={"X-Dev-Actor-Id": owner_id},
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["status"] == "running"  # serialized before the background task mutates the row
    assert body["role"] == "researcher"
    run_id = body["id"]

    trace = await _poll_until_terminal(client, run_id)
    assert trace["status"] == "completed"
    assert trace["ran_count"] == 1
    assert trace["tokens_used"] == 17
    landed = [s for s in trace["steps"] if s["status"] == "landed"]
    assert len(landed) == 1
    assert landed[0]["checkpoint_id"]
    assert trace["branch_id"]  # landed on the forked agent line

    # The list surface shows it (newest-first).
    listing = await client.get(f"/api/v1/projects/{project_id}/threads/{thread_id}/agent-runs")
    assert listing.status_code == 200, listing.text
    assert any(r["id"] == run_id for r in listing.json())


async def test_unassigned_role_is_commissioned_then_fails_on_the_trace(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    internal_funder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "agent_loop_enabled", True)
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await _project_owned_by(client, owner_id, "ar-norole")
    thread_id = await _thread(client, project_id, owner_id)
    # Deliberately assign NO model to 'researcher'.

    # A planner that would explode if called — the unassigned-role branch must short-circuit before
    # planning, so this proves both "commission accepted" and "planner never reached".
    monkeypatch.setattr(
        agent_run_service,
        "background_executor",
        BackgroundExecutor(
            session_factory=session_factory,
            planner=_raising_planner(AgentLlmError("planner must not be called")),
        ),
    )

    resp = await client.post(
        f"/api/v1/projects/{project_id}/threads/{thread_id}/agent-runs",
        json={"role": "researcher"},
        headers={"X-Dev-Actor-Id": owner_id},
    )
    assert resp.status_code == 202, resp.text  # commission is accepted (Decision #7)
    run_id = resp.json()["id"]

    trace = await _poll_until_terminal(client, run_id)
    assert trace["status"] == "failed"
    assert "no model assigned" in (trace["error"] or "")
    assert trace["ran_count"] == 0
