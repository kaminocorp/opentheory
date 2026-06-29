"""DB-backed tests for project stewardship — ownership, self-edit, membership (0.8.1).

Covers: project creation now records the creator's **account** as the ``OWNER`` ``ProjectMember``
plus a ``create_project`` ``Contribution`` (and an account-less dev actor creates an *ownerless*
project with no contribution — the documented dev-only path); the ``PATCH /projects/{id}`` authz
matrix (owner ✓ / admin ✓ / non-member ``403``; anon ``401`` is the DB-free gate in
``test_projects.py``); ``background`` round-trips + nullable; the public member list omits email;
the single-owner partial index; and owner-only member remove / role-transfer. These run only when a
database is configured (``TEST_DATABASE_URL``).

Acting users are built the Account-owns-Actor way via the ``internal_funder`` fixture (an Account +
a linked ``human`` Actor) with ``roles=()`` — a plain account-backed user. Admin memberships are
inserted directly (the invite flow lands in 0.8.3).
"""

from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.contribution import Contribution
from app.models.enums import ProjectRole
from app.models.project_member import ProjectMember


async def _members(session, project_id: str) -> list[ProjectMember]:  # type: ignore[no-untyped-def]
    result = await session.execute(
        select(ProjectMember).where(ProjectMember.project_id == UUID(project_id))
    )
    return list(result.scalars())


async def _accountless_actor(client: AsyncClient, display_name: str = "Dev") -> str:
    resp = await client.post(
        "/api/v1/actors", json={"type": "human", "display_name": display_name}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _create_project(
    client: AsyncClient, actor_id: str | None, *, slug: str = "stewardship", title: str = "Proj"
) -> dict:
    headers = {"X-Dev-Actor-Id": actor_id} if actor_id else {}
    resp = await client.post(
        "/api/v1/projects",
        json={"title": title, "slug": slug, "question": "What is X?"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_create_records_owner_and_contribution(
    client: AsyncClient, session_factory: async_sessionmaker, internal_funder
) -> None:
    actor_id, account_id = await internal_funder(client, roles=(), display_name="Owner")
    project = await _create_project(client, actor_id, slug="owned")
    project_id = project["id"]
    assert project["background"] is None  # new field, defaults null

    async with session_factory() as session:
        members = await _members(session, project_id)
        assert len(members) == 1
        assert str(members[0].account_id) == account_id
        assert members[0].role == ProjectRole.OWNER
        # The owner self-references as the inviter on create.
        assert str(members[0].invited_by_account_id) == account_id

        contribs = (
            (
                await session.execute(
                    select(Contribution).where(Contribution.project_id == UUID(project_id))
                )
            )
            .scalars()
            .all()
        )
        assert len(contribs) == 1
        assert contribs[0].action == "create_project"
        # The *act* is the actor's (provenance), even though ownership is the account's.
        assert str(contribs[0].actor_id) == actor_id
        assert contribs[0].target_type == "project"
        assert str(contribs[0].target_id) == project_id

    # The public member list surfaces the owner.
    members_resp = await client.get(f"/api/v1/projects/{project_id}/members")
    assert members_resp.status_code == 200
    rows = members_resp.json()
    assert [r["role"] for r in rows] == ["owner"]
    assert rows[0]["account"]["id"] == account_id


async def test_accountless_creator_makes_ownerless_project(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    # An account-less dev/system actor has no principal that can own, so it creates an ownerless
    # project and records no contribution (the documented dev-only path; production actors always
    # have an account). This keeps the legacy/dev behaviour green.
    actor_id = await _accountless_actor(client)
    project = await _create_project(client, actor_id, slug="ownerless")

    async with session_factory() as session:
        members = (await session.execute(select(ProjectMember))).scalars().all()
        assert members == []
        contribs = (await session.execute(select(Contribution))).scalars().all()
        assert contribs == []

    members_resp = await client.get(f"/api/v1/projects/{project['id']}/members")
    assert members_resp.json() == []


async def test_patch_authz_matrix(
    client: AsyncClient, session_factory: async_sessionmaker, internal_funder
) -> None:
    owner_actor, owner_account = await internal_funder(client, roles=(), display_name="Owner")
    admin_actor, admin_account = await internal_funder(client, roles=(), display_name="Admin")
    stranger_actor, _ = await internal_funder(client, roles=(), display_name="Stranger")
    project = await _create_project(client, owner_actor, slug="authz")
    project_id = project["id"]

    # Insert an ADMIN membership directly (the invite flow lands in 0.8.3).
    async with session_factory() as session:
        session.add(
            ProjectMember(
                project_id=UUID(project_id),
                account_id=UUID(admin_account),
                role=ProjectRole.ADMIN,
                invited_by_account_id=UUID(owner_account),
            )
        )
        await session.commit()

    # Owner can edit.
    r = await client.patch(
        f"/api/v1/projects/{project_id}",
        json={"title": "By owner"},
        headers={"X-Dev-Actor-Id": owner_actor},
    )
    assert r.status_code == 200, r.text
    assert r.json()["title"] == "By owner"

    # Admin can edit.
    r = await client.patch(
        f"/api/v1/projects/{project_id}",
        json={"question": "By admin?"},
        headers={"X-Dev-Actor-Id": admin_actor},
    )
    assert r.status_code == 200, r.text
    assert r.json()["question"] == "By admin?"

    # A signed-in non-member cannot.
    r = await client.patch(
        f"/api/v1/projects/{project_id}",
        json={"title": "By stranger"},
        headers={"X-Dev-Actor-Id": stranger_actor},
    )
    assert r.status_code == 403, r.text

    # Missing project → 404 (owner credential, unknown id).
    r = await client.patch(
        "/api/v1/projects/00000000-0000-0000-0000-000000000000",
        json={"title": "ghost"},
        headers={"X-Dev-Actor-Id": owner_actor},
    )
    assert r.status_code == 404, r.text


async def test_background_roundtrips_and_nullable(
    client: AsyncClient, internal_funder
) -> None:
    owner_actor, _ = await internal_funder(client, roles=(), display_name="Owner")
    project = await _create_project(client, owner_actor, slug="bg")
    project_id = project["id"]
    md = "# Briefing\n\nDeep **context** with a [link](https://example.com)."

    # Set background.
    r = await client.patch(
        f"/api/v1/projects/{project_id}",
        json={"background": md},
        headers={"X-Dev-Actor-Id": owner_actor},
    )
    assert r.status_code == 200, r.text
    assert r.json()["background"] == md
    # It persists on a fresh read.
    assert (await client.get(f"/api/v1/projects/{project_id}")).json()["background"] == md

    # Explicit null clears it (exclude_unset: an explicitly-sent null is applied).
    r = await client.patch(
        f"/api/v1/projects/{project_id}",
        json={"background": None},
        headers={"X-Dev-Actor-Id": owner_actor},
    )
    assert r.status_code == 200, r.text
    assert r.json()["background"] is None

    # Omitting a field leaves it untouched (partial update).
    r = await client.patch(
        f"/api/v1/projects/{project_id}",
        json={"title": "Renamed only"},
        headers={"X-Dev-Actor-Id": owner_actor},
    )
    assert r.json()["title"] == "Renamed only"
    assert r.json()["background"] is None  # still cleared, not reset


async def test_member_list_omits_pii(client: AsyncClient, internal_funder) -> None:
    owner_actor, _ = await internal_funder(client, roles=("internal",), display_name="Owner")
    project = await _create_project(client, owner_actor, slug="pii")

    rows = (await client.get(f"/api/v1/projects/{project['id']}/members")).json()
    assert len(rows) == 1
    account = rows[0]["account"]
    # Privacy-safe AccountSummary only — even though this owner has roles + (implicitly) PII fields.
    assert set(account.keys()) == {"id", "display_name"}
    assert "email" not in account
    assert "roles" not in account
    assert "external_id" not in account


async def test_single_owner_index_rejects_second_owner(
    client: AsyncClient, session_factory: async_sessionmaker, internal_funder
) -> None:
    owner_actor, _ = await internal_funder(client, roles=(), display_name="Owner")
    _, other_account = await internal_funder(client, roles=(), display_name="Other")
    project = await _create_project(client, owner_actor, slug="oneowner")

    # A second OWNER for the same project violates the uq_project_one_owner partial unique index.
    async with session_factory() as session:
        session.add(
            ProjectMember(
                project_id=UUID(project["id"]),
                account_id=UUID(other_account),
                role=ProjectRole.OWNER,
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_owner_remove_and_role_transfer(
    client: AsyncClient, session_factory: async_sessionmaker, internal_funder
) -> None:
    owner_actor, owner_account = await internal_funder(client, roles=(), display_name="Owner")
    admin_actor, admin_account = await internal_funder(client, roles=(), display_name="Admin")
    project = await _create_project(client, owner_actor, slug="govern")
    project_id = project["id"]

    async with session_factory() as session:
        session.add(
            ProjectMember(
                project_id=UUID(project_id),
                account_id=UUID(admin_account),
                role=ProjectRole.ADMIN,
                invited_by_account_id=UUID(owner_account),
            )
        )
        await session.commit()

    # An admin cannot remove a member (owner-only).
    r = await client.delete(
        f"/api/v1/projects/{project_id}/members/{owner_account}",
        headers={"X-Dev-Actor-Id": admin_actor},
    )
    assert r.status_code == 403, r.text

    # The owner cannot remove themselves while sole owner.
    r = await client.delete(
        f"/api/v1/projects/{project_id}/members/{owner_account}",
        headers={"X-Dev-Actor-Id": owner_actor},
    )
    assert r.status_code == 400, r.text

    # Nor can the sole owner demote *themselves* to admin — that would orphan the project (zero
    # owners → ungovernable). The only exit from ownership is a transfer (below). (F1, 0.8.2.)
    r = await client.patch(
        f"/api/v1/projects/{project_id}/members/{owner_account}",
        json={"role": "admin"},
        headers={"X-Dev-Actor-Id": owner_actor},
    )
    assert r.status_code == 400, r.text

    # The owner transfers ownership to the admin → prior owner demoted to admin in the same txn.
    r = await client.patch(
        f"/api/v1/projects/{project_id}/members/{admin_account}",
        json={"role": "owner"},
        headers={"X-Dev-Actor-Id": owner_actor},
    )
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "owner"

    async with session_factory() as session:
        rows = await _members(session, project_id)
        by_account = {str(m.account_id): m.role for m in rows}
        assert by_account[admin_account] == ProjectRole.OWNER
        assert by_account[owner_account] == ProjectRole.ADMIN  # demoted, single-owner preserved

    # The new owner can now remove the demoted ex-owner.
    r = await client.delete(
        f"/api/v1/projects/{project_id}/members/{owner_account}",
        headers={"X-Dev-Actor-Id": admin_actor},
    )
    assert r.status_code == 204, r.text


async def test_duplicate_slug_conflicts(client: AsyncClient, internal_funder) -> None:
    # A colliding slug (the immutable URL id) is a clean 409, not a leaked 500 from the raw unique
    # constraint violation. (0.8.2 — create path translates the IntegrityError.)
    owner_actor, _ = await internal_funder(client, roles=(), display_name="Owner")
    await _create_project(client, owner_actor, slug="dup", title="First")

    resp = await client.post(
        "/api/v1/projects",
        json={"title": "Second", "slug": "dup", "question": "What is Y?"},
        headers={"X-Dev-Actor-Id": owner_actor},
    )
    assert resp.status_code == 409, resp.text
