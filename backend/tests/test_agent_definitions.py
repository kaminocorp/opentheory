"""0.59.0 — agent definition catalog, deploy-time pointer, family rollup."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.deps import AGENT_SESSION_HTTP_DETAIL
from app.core.config import settings
from app.models.actor import Actor
from app.models.checkpoint import Checkpoint
from app.models.compute_debit import ComputeDebit
from app.models.enums import (
    ComputeDebitKind,
    ComputeDebitRateSource,
    ProjectAgentStatus,
    ValidationOutcome,
)
from app.models.validation import Validation
from app.services.agent_actors import AGENT_ACTOR_DISPLAY_NAME, get_or_create_project_agent_actor
from app.services.agent_definitions import CONFIG_FINGERPRINT_KEYS, config_fingerprint
from tests.principals import create_owned_project

TEST_SECRET = "test-agent-session-secret-0.59.0-32b!!"


def _headers(actor_id: str) -> dict[str, str]:
    return {"X-Dev-Actor-Id": actor_id}


@pytest.fixture
def agent_secret(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "agent_session_jwt_secret", TEST_SECRET)
    monkeypatch.setattr(settings, "agent_session_max_ttl_seconds", 2_592_000)
    return TEST_SECRET


def test_fingerprint_is_stable_and_ignores_display_keys() -> None:
    left = {"model_id": "m", "harness_pin": "0.1.5rc1", "extra": "nope"}
    right = {"model_id": "m", "harness_pin": "0.1.5rc1", "notes": "rename"}
    assert config_fingerprint(left) == config_fingerprint(right)
    changed = {"model_id": "other", "harness_pin": "0.1.5rc1"}
    assert config_fingerprint(left) != config_fingerprint(changed)
    assert CONFIG_FINGERPRINT_KEYS == (
        "model_id",
        "harness_pin",
        "cordis_inventory",
        "persona_hash",
    )


async def test_catalog_create_version_patch_and_ownership(
    client: AsyncClient,
    internal_funder,
) -> None:
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    eve_id, _ = await internal_funder(client, roles=(), display_name="Eve")
    created = await client.post(
        "/api/v1/agent-definitions",
        json={
            "display_name": "DeepSeek researcher",
            "config": {"model_id": "deepseek/chat", "harness_pin": "0.1.5rc1"},
        },
        headers=_headers(owner_id),
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["version"] == 1
    assert body["display_name"] == "DeepSeek researcher"
    family_id = body["family_id"]
    v1_id = body["id"]

    listed = await client.get("/api/v1/agent-definitions", headers=_headers(owner_id))
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    eve_list = await client.get("/api/v1/agent-definitions", headers=_headers(eve_id))
    assert eve_list.status_code == 200
    assert eve_list.json() == []

    eve_get = await client.get(
        f"/api/v1/agent-definitions/{v1_id}", headers=_headers(eve_id)
    )
    assert eve_get.status_code == 404

    patched = await client.patch(
        f"/api/v1/agent-definitions/{v1_id}",
        json={"display_name": "DeepSeek researcher (catalog)"},
        headers=_headers(owner_id),
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["version"] == 1
    assert patched.json()["id"] == v1_id
    assert patched.json()["config_fingerprint"] == body["config_fingerprint"]

    same = await client.post(
        f"/api/v1/agent-definitions/{v1_id}/versions",
        json={"config": {"model_id": "deepseek/chat", "harness_pin": "0.1.5rc1"}},
        headers=_headers(owner_id),
    )
    assert same.status_code == 409

    versioned = await client.post(
        f"/api/v1/agent-definitions/{v1_id}/versions",
        json={
            "display_name": "DeepSeek researcher v2",
            "config": {"model_id": "deepseek/reasoner", "harness_pin": "0.1.5rc1"},
        },
        headers=_headers(owner_id),
    )
    assert versioned.status_code == 201, versioned.text
    assert versioned.json()["family_id"] == family_id
    assert versioned.json()["version"] == 2
    assert versioned.json()["id"] != v1_id

    eve_version = await client.post(
        f"/api/v1/agent-definitions/{v1_id}/versions",
        json={"config": {"model_id": "stolen"}},
        headers=_headers(eve_id),
    )
    assert eve_version.status_code == 404


async def test_deploy_pointer_upgrade_and_research_crew_rejected(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    internal_funder,
) -> None:
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await create_owned_project(client, owner_id, "catalog-deploy")
    created = await client.post(
        "/api/v1/agent-definitions",
        json={"display_name": "Kind", "config": {"model_id": "a"}},
        headers=_headers(owner_id),
    )
    assert created.status_code == 201, created.text
    v1 = created.json()
    v2 = (
        await client.post(
            f"/api/v1/agent-definitions/{v1['id']}/versions",
            json={"display_name": "Kind v2", "config": {"model_id": "b"}},
            headers=_headers(owner_id),
        )
    ).json()

    crew = await client.post(
        f"/api/v1/projects/{project_id}/agents",
        json={
            "display_name": AGENT_ACTOR_DISPLAY_NAME,
            "reuse_research_crew": True,
            "agent_definition_id": v1["id"],
        },
        headers=_headers(owner_id),
    )
    assert crew.status_code == 422, crew.text

    deployed = await client.post(
        f"/api/v1/projects/{project_id}/agents",
        json={
            "display_name": "Seat",
            "agent_definition_id": v1["id"],
            "token_budget_cap": 40,
        },
        headers=_headers(owner_id),
    )
    assert deployed.status_code == 201, deployed.text
    seat = deployed.json()
    assert seat["agent_definition_id"] == v1["id"]
    assert seat["family_id"] == v1["family_id"]
    assert seat["definition_version"] == 1
    assert seat["definition_display_name"] == "Kind"
    assert seat["token_budget_cap"] == 40
    old_actor = seat["actor_id"]

    same_version = await client.post(
        f"/api/v1/projects/{project_id}/agents/{old_actor}/upgrade",
        json={"agent_definition_id": v1["id"]},
        headers=_headers(owner_id),
    )
    assert same_version.status_code == 409

    other = await client.post(
        "/api/v1/agent-definitions",
        json={"display_name": "Other family", "config": {"model_id": "z"}},
        headers=_headers(owner_id),
    )
    assert other.status_code == 201
    cross = await client.post(
        f"/api/v1/projects/{project_id}/agents/{old_actor}/upgrade",
        json={"agent_definition_id": other.json()["id"]},
        headers=_headers(owner_id),
    )
    assert cross.status_code == 409

    upgraded = await client.post(
        f"/api/v1/projects/{project_id}/agents/{old_actor}/upgrade",
        json={"agent_definition_id": v2["id"]},
        headers=_headers(owner_id),
    )
    assert upgraded.status_code == 201, upgraded.text
    new_seat = upgraded.json()
    assert new_seat["actor_id"] != old_actor
    assert new_seat["agent_definition_id"] == v2["id"]
    assert new_seat["definition_version"] == 2
    assert new_seat["token_budget_cap"] == 40
    assert new_seat["status"] == ProjectAgentStatus.ACTIVE.value

    roster = await client.get(
        f"/api/v1/projects/{project_id}/agents", headers=_headers(owner_id)
    )
    assert roster.status_code == 200
    by_id = {row["actor_id"]: row for row in roster.json()}
    assert by_id[old_actor]["status"] == ProjectAgentStatus.REVOKED.value
    assert by_id[old_actor]["agent_definition_id"] == v1["id"]
    assert by_id[new_seat["actor_id"]]["status"] == ProjectAgentStatus.ACTIVE.value

    async with session_factory() as session:
        old = await session.get(Actor, UUID(old_actor))
        assert old is not None
        assert str(old.agent_definition_id) == v1["id"]
        old.agent_definition_id = UUID(v2["id"])
        with pytest.raises(ValueError, match="deploy-time only"):
            await session.flush()


async def test_family_rollup_is_read_join(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    internal_funder,
) -> None:
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    member_id, member_account = await internal_funder(client, roles=(), display_name="Member")
    eve_id, _ = await internal_funder(client, roles=(), display_name="Eve")
    project_id = await create_owned_project(client, owner_id, "catalog-rollup")
    from app.models.enums import ProjectRole
    from app.models.project_member import ProjectMember

    async with session_factory() as session:
        session.add(
            ProjectMember(
                project_id=UUID(project_id),
                account_id=UUID(member_account),
                role=ProjectRole.ADMIN,
            )
        )
        await session.commit()

    created = await client.post(
        "/api/v1/agent-definitions",
        json={"display_name": "Kind", "config": {"model_id": "a"}},
        headers=_headers(owner_id),
    )
    assert created.status_code == 201, created.text
    definition = created.json()
    deployed = await client.post(
        f"/api/v1/projects/{project_id}/agents",
        json={"display_name": "Seat", "agent_definition_id": definition["id"]},
        headers=_headers(owner_id),
    )
    assert deployed.status_code == 201, deployed.text
    agent_id = deployed.json()["actor_id"]

    async with session_factory() as session:
        checkpoint = Checkpoint(
            project_id=UUID(project_id),
            author_id=UUID(agent_id),
            summary="authored",
        )
        session.add(checkpoint)
        await session.flush()
        session.add(
            Validation(
                project_id=UUID(project_id),
                actor_id=UUID(owner_id),
                checkpoint_id=checkpoint.id,
                outcome=ValidationOutcome.PASSED,
            )
        )
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
                notes="dark-loop; billed",
            )
        )
        await session.commit()

    rollup = await client.get(
        f"/api/v1/agent-definitions/families/{definition['family_id']}",
        headers=_headers(owner_id),
    )
    assert rollup.status_code == 200, rollup.text
    payload = rollup.json()
    assert payload["checkpoints_authored"] == 1
    assert payload["incoming_validations"] == 1
    assert payload["tokens_billed"] == 40
    assert len(payload["actors"]) == 1
    assert payload["actors"][0]["actor_id"] == agent_id

    member_read = await client.get(
        f"/api/v1/agent-definitions/families/{definition['family_id']}",
        headers=_headers(member_id),
    )
    assert member_read.status_code == 200, member_read.text

    eve_read = await client.get(
        f"/api/v1/agent-definitions/families/{definition['family_id']}",
        headers=_headers(eve_id),
    )
    assert eve_read.status_code == 404


async def test_catalog_http_refuses_agent_session(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    internal_funder,
    agent_secret,
) -> None:
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await create_owned_project(client, owner_id, "catalog-http")
    async with session_factory() as session:
        actor = await get_or_create_project_agent_actor(session, UUID(project_id))
        await session.commit()
        agent_id = str(actor.id)
    minted = await client.post(
        f"/api/v1/projects/{project_id}/agents/{agent_id}/tokens",
        json={},
        headers=_headers(owner_id),
    )
    assert minted.status_code == 201, minted.text
    bearer = {"Authorization": f"Bearer {minted.json()['token']}"}
    listed = await client.get("/api/v1/agent-definitions", headers=bearer)
    assert listed.status_code == 403
    assert listed.json()["detail"] == AGENT_SESSION_HTTP_DETAIL
    created = await client.post(
        "/api/v1/agent-definitions",
        json={"display_name": "Nope", "config": {}},
        headers=bearer,
    )
    assert created.status_code == 403
