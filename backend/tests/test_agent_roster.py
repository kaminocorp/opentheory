"""0.57.0 — Crew roster list / deploy / lifecycle, blame sponsor, ops actor_*.

DB-gated. Per-agent cap enforcement and the definition catalog stay out.
"""

from decimal import Decimal
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import settings
from app.harness.live_mcp import invoke
from app.models.compute_debit import ComputeDebit
from app.models.enums import (
    ComputeDebitKind,
    ComputeDebitRateSource,
    ProjectAgentStatus,
    ProjectRole,
)
from app.models.project_member import ProjectMember
from app.services.agent_actors import AGENT_ACTOR_DISPLAY_NAME, get_or_create_project_agent_actor
from app.services.harness_meter import SESSION_NOTES
from tests.principals import create_owned_project

TEST_SECRET = "test-agent-session-secret-0.57.0-32b!!"


def _headers(actor_id: str) -> dict[str, str]:
    return {"X-Dev-Actor-Id": actor_id}


@pytest.fixture
def agent_secret(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "agent_session_jwt_secret", TEST_SECRET)
    monkeypatch.setattr(settings, "agent_session_max_ttl_seconds", 2_592_000)
    return TEST_SECRET


async def _roster_crew(session_factory: async_sessionmaker, project_id: str) -> str:
    async with session_factory() as session:
        actor = await get_or_create_project_agent_actor(session, UUID(project_id))
        await session.commit()
        return str(actor.id)


async def test_roster_list_is_members_only_and_includes_revoked_and_spend(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    internal_funder,
    agent_secret,
) -> None:
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    outsider_id, _ = await internal_funder(client, roles=(), display_name="Eve")
    project_id = await create_owned_project(client, owner_id, "roster-list")
    agent_id = await _roster_crew(session_factory, project_id)

    minted = await client.post(
        f"/api/v1/projects/{project_id}/agents/{agent_id}/tokens",
        json={},
        headers=_headers(owner_id),
    )
    assert minted.status_code == 201, minted.text

    async with session_factory() as session:
        session.add(
            ComputeDebit(
                project_id=UUID(project_id),
                actor_id=UUID(agent_id),
                tokens_used=40,
                amount=Decimal("0.20"),
                currency="USD",
                rate_per_1k=Decimal("5"),
                rate_source=ComputeDebitRateSource.BLENDED_FALLBACK,
                kind=ComputeDebitKind.PLANNING,
                notes=f"{SESSION_NOTES}; billed",
            )
        )
        await session.commit()

    missing = await client.get(f"/api/v1/projects/{project_id}/agents")
    assert missing.status_code == 401

    outsider = await client.get(
        f"/api/v1/projects/{project_id}/agents",
        headers=_headers(outsider_id),
    )
    assert outsider.status_code == 403

    listed = await client.get(
        f"/api/v1/projects/{project_id}/agents",
        headers=_headers(owner_id),
    )
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert len(body) == 1
    row = body[0]
    assert row["actor_id"] == agent_id
    assert row["display_name"] == AGENT_ACTOR_DISPLAY_NAME
    assert row["status"] == ProjectAgentStatus.ACTIVE.value
    assert row["responsible"]["display_name"] == "Owner"
    assert row["tokens_used"] == 40
    assert Decimal(row["amount"]) == Decimal("0.20")
    assert len(row["live_tokens"]) == 1
    assert row["live_tokens"][0]["jti"] == minted.json()["jti"]
    assert "token_hash" not in row
    assert "token" not in row

    revoked = await client.patch(
        f"/api/v1/projects/{project_id}/agents/{agent_id}",
        json={"status": "revoked"},
        headers=_headers(owner_id),
    )
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["status"] == ProjectAgentStatus.REVOKED.value
    assert revoked.json()["live_tokens"] == []

    still = await client.get(
        f"/api/v1/projects/{project_id}/agents",
        headers=_headers(owner_id),
    )
    assert still.status_code == 200
    assert still.json()[0]["status"] == ProjectAgentStatus.REVOKED.value
    assert still.json()[0]["tokens_used"] == 40


async def test_deploy_named_agent_and_reuse_research_crew_conflict(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    internal_funder,
) -> None:
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await create_owned_project(client, owner_id, "roster-deploy")

    named = await client.post(
        f"/api/v1/projects/{project_id}/agents",
        json={"display_name": "DeepSeek researcher"},
        headers=_headers(owner_id),
    )
    assert named.status_code == 201, named.text
    assert named.json()["display_name"] == "DeepSeek researcher"
    assert named.json()["status"] == ProjectAgentStatus.ACTIVE.value

    crew = await client.post(
        f"/api/v1/projects/{project_id}/agents",
        json={"display_name": "Research crew", "reuse_research_crew": True},
        headers=_headers(owner_id),
    )
    assert crew.status_code == 201, crew.text
    assert crew.json()["display_name"] == AGENT_ACTOR_DISPLAY_NAME

    again = await client.post(
        f"/api/v1/projects/{project_id}/agents",
        json={"display_name": "Research crew", "reuse_research_crew": True},
        headers=_headers(owner_id),
    )
    assert again.status_code == 409


async def test_suspend_resume_and_admin_cannot_resume(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    internal_funder,
) -> None:
    owner_id, owner_account = await internal_funder(client, roles=(), display_name="Owner")
    admin_id, admin_account = await internal_funder(client, roles=(), display_name="Admin")
    project_id = await create_owned_project(client, owner_id, "roster-life")
    async with session_factory() as session:
        session.add(
            ProjectMember(
                project_id=UUID(project_id),
                account_id=UUID(admin_account),
                role=ProjectRole.ADMIN,
            )
        )
        await session.commit()

    deployed = await client.post(
        f"/api/v1/projects/{project_id}/agents",
        json={"display_name": "Field agent"},
        headers=_headers(admin_id),
    )
    assert deployed.status_code == 201, deployed.text
    agent_id = deployed.json()["actor_id"]

    suspended = await client.patch(
        f"/api/v1/projects/{project_id}/agents/{agent_id}",
        json={"status": "suspended"},
        headers=_headers(admin_id),
    )
    assert suspended.status_code == 200, suspended.text
    assert suspended.json()["status"] == ProjectAgentStatus.SUSPENDED.value

    admin_resume = await client.patch(
        f"/api/v1/projects/{project_id}/agents/{agent_id}",
        json={"status": "active"},
        headers=_headers(admin_id),
    )
    assert admin_resume.status_code == 403

    resumed = await client.patch(
        f"/api/v1/projects/{project_id}/agents/{agent_id}",
        json={"status": "active"},
        headers=_headers(owner_id),
    )
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["status"] == ProjectAgentStatus.ACTIVE.value
    assert resumed.json()["responsible"]["id"] == owner_account

    revoked = await client.patch(
        f"/api/v1/projects/{project_id}/agents/{agent_id}",
        json={"status": "revoked"},
        headers=_headers(owner_id),
    )
    assert revoked.status_code == 200
    resume_revoked = await client.patch(
        f"/api/v1/projects/{project_id}/agents/{agent_id}",
        json={"status": "active"},
        headers=_headers(owner_id),
    )
    assert resume_revoked.status_code == 409


async def test_blame_and_checkpoint_carry_sponsor(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    internal_funder,
    agent_secret,
) -> None:
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await create_owned_project(client, owner_id, "roster-blame")
    agent_id = await _roster_crew(session_factory, project_id)
    minted = await client.post(
        f"/api/v1/projects/{project_id}/agents/{agent_id}/tokens",
        json={},
        headers=_headers(owner_id),
    )
    assert minted.status_code == 201, minted.text
    thread = await client.post(
        f"/api/v1/projects/{project_id}/threads",
        json={"title": "T", "question": "q?"},
        headers=_headers(owner_id),
    )
    assert thread.status_code == 201
    claim = await client.post(
        f"/api/v1/threads/{thread.json()['id']}/claims",
        json={"kind": "hypothesis", "statement": "X holds."},
        headers=_headers(owner_id),
    )
    assert claim.status_code == 201
    result = await invoke(
        "create_checkpoint",
        {
            "project_id": project_id,
            "thread_id": thread.json()["id"],
            "summary": "agent asserted",
            "refs": [
                {
                    "target_type": "claim",
                    "target_id": claim.json()["id"],
                    "role": "asserted",
                }
            ],
        },
        session_factory=session_factory,
        env={"OPENTHEORY_ACTOR_JWT": minted.json()["token"]},
    )
    assert result["minted"] is True, result

    checkpoint = await client.get(f"/api/v1/checkpoints/{result['checkpoint_id']}")
    assert checkpoint.status_code == 200, checkpoint.text
    body = checkpoint.json()
    assert body["author"]["id"] == agent_id
    assert body["author"]["type"] == "agent"
    assert body["sponsored_by_actor_id"] == owner_id
    assert body["sponsored_by"]["id"] == owner_id
    assert body["sponsored_by"]["type"] == "human"
    assert body["sponsored_by"]["display_name"] == "Owner"

    blame = await client.get(
        f"/api/v1/projects/{project_id}/claims/{claim.json()['id']}/blame"
    )
    assert blame.status_code == 200, blame.text
    step = blame.json()["chain"][0]
    assert step["author"]["id"] == agent_id
    assert step["author"]["type"] == "agent"
    assert step["sponsor"]["id"] == owner_id
    assert step["sponsor"]["type"] == "human"

    human = await client.post(
        f"/api/v1/projects/{project_id}/checkpoints",
        json={
            "summary": "human follow-up",
            "thread_id": thread.json()["id"],
            "refs": [
                {
                    "target_type": "claim",
                    "target_id": claim.json()["id"],
                    "role": "noted",
                }
            ],
        },
        headers=_headers(owner_id),
    )
    assert human.status_code == 201, human.text
    assert human.json()["sponsored_by"] is None
    assert human.json()["sponsored_by_actor_id"] is None


async def test_ops_actor_fields_and_spend_by_agent(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    internal_funder,
) -> None:
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await create_owned_project(client, owner_id, "roster-ops")
    agent_id = await _roster_crew(session_factory, project_id)

    async with session_factory() as session:
        session.add(
            ComputeDebit(
                project_id=UUID(project_id),
                actor_id=UUID(agent_id),
                tokens_used=80,
                amount=Decimal("0.40"),
                currency="USD",
                rate_per_1k=Decimal("5"),
                rate_source=ComputeDebitRateSource.BLENDED_FALLBACK,
                kind=ComputeDebitKind.PLANNING,
                notes=f"{SESSION_NOTES}; rate fallback: blended_fallback",
            )
        )
        session.add(
            ComputeDebit(
                project_id=UUID(project_id),
                actor_id=UUID(agent_id),
                tokens_used=500,
                amount=Decimal("0"),
                currency="USD",
                rate_per_1k=Decimal("0"),
                rate_source=ComputeDebitRateSource.BLENDED_FALLBACK,
                kind=ComputeDebitKind.PLANNING,
                notes=f"{SESSION_NOTES}; daily_cap_hold; hold_id=00000000-0000-0000-0000-000000000001",
            )
        )
        await session.commit()

    resp = await client.get(f"/api/v1/projects/{project_id}/ops")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    spend = [row for row in body["recent_turns"] if row["kind"] == "spend"]
    assert len(spend) == 1
    assert spend[0]["actor_id"] == agent_id
    assert spend[0]["actor_display_name"] == AGENT_ACTOR_DISPLAY_NAME
    assert spend[0]["actor_type"] == "agent"
    assert body["last_turn"]["actor_id"] == agent_id
    assert body["last_turn"]["actor_display_name"] == AGENT_ACTOR_DISPLAY_NAME
    assert len(body["spend_by_agent"]) == 1
    grouped = body["spend_by_agent"][0]
    assert grouped["actor_id"] == agent_id
    assert grouped["tokens_used"] == 80
    assert Decimal(grouped["amount"]) == Decimal("0.40")
    assert grouped["turn_count"] == 1
