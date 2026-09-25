"""The campaign API surface (0.25.0) — start, cancel, poll, and the gate edges.

DB-free gates run in the default suite (they reject before any DB access):

- **dark launch** — with ``agent_loop_enabled`` off, an unauthenticated ``POST`` is
  ``404`` (not ``401``);
- **auth** — with the flag on, an unauthenticated ``POST`` is ``401``.

The rest is DB-backed (skips without ``TEST_DATABASE_URL``).
"""

import asyncio
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agent.planner import PlannedRun, PlanResult
from app.core.config import settings
from app.services import campaigns as campaign_service
from app.services.campaigns import CampaignExecutor
from tests.agent.test_orchestration_api import (
    _assign_model,
    _claim,
    _project_owned_by,
    _stub_planner,
    _thread,
    _thread_checkpoint,
)

_BOGUS = "00000000-0000-0000-0000-000000000000"


def test_dark_launch_post_is_404_when_disabled(dbfree_client: TestClient) -> None:
    resp = dbfree_client.post(
        f"/api/v1/projects/{_BOGUS}/campaigns",
        json={"role": "researcher"},
    )
    assert resp.status_code == 404, resp.text


def test_dark_launch_get_is_404_when_disabled(dbfree_client: TestClient) -> None:
    resp = dbfree_client.get(f"/api/v1/campaigns/{_BOGUS}")
    assert resp.status_code == 404, resp.text


def test_dark_launch_cancel_is_404_when_disabled(dbfree_client: TestClient) -> None:
    resp = dbfree_client.post(f"/api/v1/campaigns/{_BOGUS}/cancel")
    assert resp.status_code == 404, resp.text


def test_unauthenticated_post_is_401_when_enabled(
    dbfree_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "agent_loop_enabled", True)
    monkeypatch.setattr(settings, "auth_dev_header_enabled", False)
    resp = dbfree_client.post(
        f"/api/v1/projects/{_BOGUS}/campaigns",
        json={"role": "researcher"},
    )
    assert resp.status_code == 401, resp.text


async def _poll_until_terminal(client: AsyncClient, campaign_id: str, tries: int = 80) -> dict:
    for _ in range(tries):
        resp = await client.get(f"/api/v1/campaigns/{campaign_id}")
        assert resp.status_code == 200, resp.text
        if resp.json()["status"] in ("completed", "failed"):
            return resp.json()
        await asyncio.sleep(0.05)
    raise AssertionError("campaign did not reach a terminal state")


async def test_non_member_is_403(
    client: AsyncClient, internal_funder, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "agent_loop_enabled", True)
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await _project_owned_by(client, owner_id, "camp-403")
    outsider_id, _ = await internal_funder(client, roles=(), display_name="Outsider")

    resp = await client.post(
        f"/api/v1/projects/{project_id}/campaigns",
        json={"role": "researcher"},
        headers={"X-Dev-Actor-Id": outsider_id},
    )
    assert resp.status_code == 403, resp.text


async def test_bad_role_is_422(
    client: AsyncClient, internal_funder, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "agent_loop_enabled", True)
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await _project_owned_by(client, owner_id, "camp-422")

    resp = await client.post(
        f"/api/v1/projects/{project_id}/campaigns",
        json={"role": "wizard"},
        headers={"X-Dev-Actor-Id": owner_id},
    )
    assert resp.status_code == 422, resp.text


async def test_full_round_trip_starts_and_polls(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    internal_funder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "agent_loop_enabled", True)
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await _project_owned_by(client, owner_id, "camp-roundtrip")
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
        campaign_service,
        "background_executor",
        CampaignExecutor(session_factory=session_factory, planner=_stub_planner(plan_result)),
    )

    resp = await client.post(
        f"/api/v1/projects/{project_id}/campaigns",
        json={"role": "researcher"},
        headers={"X-Dev-Actor-Id": owner_id},
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["status"] == "running"
    assert body["role"] == "researcher"
    campaign_id = body["id"]

    trace = await _poll_until_terminal(client, campaign_id)
    assert trace["status"] == "completed"
    assert trace["stop_reason"] == "no_open_work"
    assert trace["cycles_completed"] == 1
    assert trace["cycles"][0]["orchestration_id"]
    assert trace["cycles"][0]["stop_reason"] == "no_open_work"

    listing = await client.get(f"/api/v1/projects/{project_id}/campaigns")
    assert listing.status_code == 200, listing.text
    listed = next(r for r in listing.json() if r["id"] == campaign_id)
    assert listed["status"] == "completed"
    assert listed["cycles_completed"] == 1


async def test_cancel_via_api_stops_a_running_campaign(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    internal_funder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "agent_loop_enabled", True)
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await _project_owned_by(client, owner_id, "camp-api-cancel")

    from app.models.actor import Actor
    from app.services.campaigns import start_campaign

    async with session_factory() as session:
        actor = await session.get(Actor, UUID(owner_id))
        campaign = await start_campaign(
            session, UUID(project_id), triggered_by=actor, role="researcher"
        )
        campaign_id = str(campaign.id)

    resp = await client.post(
        f"/api/v1/campaigns/{campaign_id}/cancel",
        headers={"X-Dev-Actor-Id": owner_id},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["cancel_requested"] is True
    assert resp.json()["status"] == "running"


async def test_second_in_flight_campaign_is_409(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    internal_funder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "agent_loop_enabled", True)
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await _project_owned_by(client, owner_id, "camp-409")

    from app.models.actor import Actor
    from app.models.enums import ResearchCampaignStatus
    from app.models.research_campaign import ResearchCampaign

    async with session_factory() as session:
        actor = await session.get(Actor, UUID(owner_id))
        session.add(
            ResearchCampaign(
                project_id=UUID(project_id),
                triggered_by_actor_id=actor.id,
                role="researcher",
                status=ResearchCampaignStatus.RUNNING,
                max_cycles=8,
                error_budget=3,
            )
        )
        await session.commit()

    resp = await client.post(
        f"/api/v1/projects/{project_id}/campaigns",
        json={"role": "researcher"},
        headers={"X-Dev-Actor-Id": owner_id},
    )
    assert resp.status_code == 409, resp.text
