"""Tests for project collaboration invitations (0.8.7).

Two layers:

- **DB-free auth gates** (always run, via ``dbfree_client``): the invitee/owner-admin invitation
  endpoints reject an unauthenticated request inside the ``ActingActor`` dependency, *before* any DB
  access. Like ``test_projects.py``, these are the direct regression tests for those gates.
- **DB-backed flow** (skip without ``TEST_DATABASE_URL``): invite by ``@username`` and by email →
  ``PENDING``; unknown identifier → ``404``; self / already-member / already-pending → ``409``;
  ``GET /me/invitations`` is caller-scoped; accept mints the **admin** membership (and that admin
  can then ``PATCH`` the project) without recording any ``Contribution`` (governance ≠ credit);
  decline creates no membership; re-invite after decline resets the *same* row to ``PENDING``;
  revoke; a
  non-invitee accept/decline → ``403``; non-member invite/list → ``403``; and every read omits PII.

Acting users are built the Account-owns-Actor way (``POST /accounts`` + a linked ``human`` actor),
reading back each account's auto-generated ``@username`` so we can invite by handle.
"""

from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import settings
from app.models.contribution import Contribution

# --- DB-free auth gates (no Postgres needed) --------------------------------


def test_unauthenticated_invite_is_rejected(
    dbfree_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Production posture: the dev-header fallback is off (conftest enables it process-wide), so no
    # credential resolves and the ActingActor dependency 401s before the handler touches the DB.
    monkeypatch.setattr(settings, "auth_dev_header_enabled", False)
    resp = dbfree_client.post(
        "/api/v1/projects/00000000-0000-0000-0000-000000000000/invitations",
        json={"identifier": "@somebody"},
    )
    assert resp.status_code == 401, resp.text


def test_unauthenticated_my_invitations_is_rejected(
    dbfree_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "auth_dev_header_enabled", False)
    resp = dbfree_client.get("/api/v1/me/invitations")
    assert resp.status_code == 401, resp.text


def test_unauthenticated_accept_is_rejected(
    dbfree_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "auth_dev_header_enabled", False)
    resp = dbfree_client.post(
        "/api/v1/invitations/00000000-0000-0000-0000-000000000000/accept", json={}
    )
    assert resp.status_code == 401, resp.text


# --- DB-backed flow helpers -------------------------------------------------


async def _make_user(
    client: AsyncClient,
    display_name: str,
    *,
    email: str | None = None,
    roles: tuple[str, ...] = (),
) -> dict:
    """Create an Account (+ its primary human Actor) and read back the auto-generated handle."""
    payload: dict = {"display_name": display_name, "roles": list(roles)}
    if email is not None:
        payload["email"] = email
    acct = await client.post("/api/v1/accounts", json=payload)
    assert acct.status_code == 201, acct.text
    account = acct.json()
    actor = await client.post(
        "/api/v1/actors",
        json={"type": "human", "display_name": display_name, "account_id": account["id"]},
    )
    assert actor.status_code == 201, actor.text
    return {
        "actor_id": actor.json()["id"],
        "account_id": account["id"],
        "username": account["username"],
        "email": email,
    }


async def _create_project(
    client: AsyncClient, actor_id: str, *, slug: str = "invites", title: str = "Proj"
) -> dict:
    resp = await client.post(
        "/api/v1/projects",
        json={"title": title, "slug": slug, "question": "What is X?"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _invite(client: AsyncClient, project_id: str, actor_id: str, identifier: str):
    return await client.post(
        f"/api/v1/projects/{project_id}/invitations",
        json={"identifier": identifier},
        headers={"X-Dev-Actor-Id": actor_id},
    )


def _headers(actor_id: str) -> dict:
    return {"X-Dev-Actor-Id": actor_id}


# --- DB-backed flow ---------------------------------------------------------


async def test_invite_by_username_and_email(client: AsyncClient) -> None:
    owner = await _make_user(client, "Owner")
    bob = await _make_user(client, "Bob", email="bob@example.com")
    carol = await _make_user(client, "Carol", email="carol@example.com")
    project = await _create_project(client, owner["actor_id"], slug="invite-shapes")
    pid = project["id"]

    # By @username.
    r = await _invite(client, pid, owner["actor_id"], f"@{bob['username']}")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "pending"
    assert body["role"] == "admin"  # default
    assert body["project_title"] == project["title"]
    assert body["invitee"]["id"] == bob["account_id"]
    assert body["invited_by"]["id"] == owner["account_id"]
    # PII-safe summaries only — public handle yes, email/roles no.
    assert set(body["invitee"].keys()) == {"id", "display_name", "username"}
    assert set(body["invited_by"].keys()) == {"id", "display_name", "username"}

    # By email.
    r = await _invite(client, pid, owner["actor_id"], "carol@example.com")
    assert r.status_code == 201, r.text
    assert r.json()["invitee"]["id"] == carol["account_id"]


async def test_invite_unknown_identifier_is_404(client: AsyncClient) -> None:
    owner = await _make_user(client, "Owner")
    project = await _create_project(client, owner["actor_id"], slug="invite-404")
    r = await _invite(client, project["id"], owner["actor_id"], "@nobody_here_at_all")
    assert r.status_code == 404, r.text


async def test_self_and_duplicate_invites_conflict(client: AsyncClient) -> None:
    owner = await _make_user(client, "Owner")
    bob = await _make_user(client, "Bob", email="bob@example.com")
    project = await _create_project(client, owner["actor_id"], slug="invite-conflicts")
    pid = project["id"]

    # Inviting yourself → 409.
    r = await _invite(client, pid, owner["actor_id"], f"@{owner['username']}")
    assert r.status_code == 409, r.text

    # First invite → 201; a second while still pending → 409 (duplicate).
    assert (await _invite(client, pid, owner["actor_id"], f"@{bob['username']}")).status_code == 201
    r = await _invite(client, pid, owner["actor_id"], f"@{bob['username']}")
    assert r.status_code == 409, r.text


async def test_my_invitations_is_caller_scoped(client: AsyncClient) -> None:
    owner = await _make_user(client, "Owner")
    bob = await _make_user(client, "Bob", email="bob@example.com")
    carol = await _make_user(client, "Carol", email="carol@example.com")
    project = await _create_project(client, owner["actor_id"], slug="inbox-scope")
    pid = project["id"]
    await _invite(client, pid, owner["actor_id"], f"@{bob['username']}")
    await _invite(client, pid, owner["actor_id"], f"@{carol['username']}")

    # Bob sees only his own pending invite.
    r = await client.get("/api/v1/me/invitations", headers=_headers(bob["actor_id"]))
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["invitee"]["id"] == bob["account_id"]
    assert rows[0]["project_id"] == pid
    assert "email" not in rows[0]["invitee"]

    # The owner (the inviter) has no invitations addressed to them.
    r = await client.get("/api/v1/me/invitations", headers=_headers(owner["actor_id"]))
    assert r.json() == []


async def test_accept_creates_admin_membership_without_contribution(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    owner = await _make_user(client, "Owner")
    bob = await _make_user(client, "Bob", email="bob@example.com")
    project = await _create_project(client, owner["actor_id"], slug="accept-flow")
    pid = project["id"]
    invitation = (await _invite(client, pid, owner["actor_id"], f"@{bob['username']}")).json()

    # The owner sees the pending invite in the project-side list (privacy-safe).
    r = await client.get(f"/api/v1/projects/{pid}/invitations", headers=_headers(owner["actor_id"]))
    assert r.status_code == 200, r.text
    assert [i["invitee"]["id"] for i in r.json()] == [bob["account_id"]]

    # Bob accepts → becomes an admin member; status flips to accepted.
    r = await client.post(
        f"/api/v1/invitations/{invitation['id']}/accept", headers=_headers(bob["actor_id"])
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "accepted"

    members = (await client.get(f"/api/v1/projects/{pid}/members")).json()
    roles_by_account = {m["account"]["id"]: m["role"] for m in members}
    assert roles_by_account[bob["account_id"]] == "admin"

    # The new admin can now edit the project.
    r = await client.patch(
        f"/api/v1/projects/{pid}", json={"title": "By Bob"}, headers=_headers(bob["actor_id"])
    )
    assert r.status_code == 200, r.text
    assert r.json()["title"] == "By Bob"

    # Re-inviting an existing member → 409, and Bob's inbox is now empty.
    r = await _invite(client, pid, owner["actor_id"], f"@{bob['username']}")
    assert r.status_code == 409, r.text
    assert (
        await client.get("/api/v1/me/invitations", headers=_headers(bob["actor_id"]))
    ).json() == []

    # Guardrail: accepting an invite records NO Contribution (membership is governance, not credit).
    # Only the create_project contribution should exist for this project.
    async with session_factory() as session:
        contribs = (
            (
                await session.execute(
                    select(Contribution).where(Contribution.project_id == UUID(pid))
                )
            )
            .scalars()
            .all()
        )
        assert [c.action for c in contribs] == ["create_project"]


async def test_admin_can_invite_further_admins(client: AsyncClient) -> None:
    owner = await _make_user(client, "Owner")
    bob = await _make_user(client, "Bob", email="bob@example.com")
    carol = await _make_user(client, "Carol", email="carol@example.com")
    project = await _create_project(client, owner["actor_id"], slug="admin-invites")
    pid = project["id"]

    # Bob accepts an invite, becoming an admin.
    inv = (await _invite(client, pid, owner["actor_id"], f"@{bob['username']}")).json()
    await client.post(f"/api/v1/invitations/{inv['id']}/accept", headers=_headers(bob["actor_id"]))

    # An admin may invite further admins (Decision).
    r = await _invite(client, pid, bob["actor_id"], f"@{carol['username']}")
    assert r.status_code == 201, r.text
    assert r.json()["invited_by"]["id"] == bob["account_id"]


async def test_decline_then_reinvite_resets_same_row(client: AsyncClient) -> None:
    owner = await _make_user(client, "Owner")
    bob = await _make_user(client, "Bob", email="bob@example.com")
    project = await _create_project(client, owner["actor_id"], slug="decline-reinvite")
    pid = project["id"]
    inv = (await _invite(client, pid, owner["actor_id"], f"@{bob['username']}")).json()

    # Bob declines → no membership, status declined, inbox empties.
    r = await client.post(
        f"/api/v1/invitations/{inv['id']}/decline", headers=_headers(bob["actor_id"])
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "declined"
    members = (await client.get(f"/api/v1/projects/{pid}/members")).json()
    assert all(m["account"]["id"] != bob["account_id"] for m in members)
    assert (
        await client.get("/api/v1/me/invitations", headers=_headers(bob["actor_id"]))
    ).json() == []

    # Re-inviting resets the SAME row to pending (uq_project_invitation forbids a second row).
    r = await _invite(client, pid, owner["actor_id"], f"@{bob['username']}")
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "pending"
    assert r.json()["id"] == inv["id"]
    inbox = (await client.get("/api/v1/me/invitations", headers=_headers(bob["actor_id"]))).json()
    assert len(inbox) == 1 and inbox[0]["id"] == inv["id"]


async def test_non_invitee_cannot_accept_or_decline(client: AsyncClient) -> None:
    owner = await _make_user(client, "Owner")
    bob = await _make_user(client, "Bob", email="bob@example.com")
    stranger = await _make_user(client, "Stranger", email="stranger@example.com")
    project = await _create_project(client, owner["actor_id"], slug="invitee-only")
    pid = project["id"]
    inv = (await _invite(client, pid, owner["actor_id"], f"@{bob['username']}")).json()

    r = await client.post(
        f"/api/v1/invitations/{inv['id']}/accept", headers=_headers(stranger["actor_id"])
    )
    assert r.status_code == 403, r.text
    r = await client.post(
        f"/api/v1/invitations/{inv['id']}/decline", headers=_headers(stranger["actor_id"])
    )
    assert r.status_code == 403, r.text


async def test_revoke_pending_invitation(client: AsyncClient) -> None:
    owner = await _make_user(client, "Owner")
    bob = await _make_user(client, "Bob", email="bob@example.com")
    project = await _create_project(client, owner["actor_id"], slug="revoke-flow")
    pid = project["id"]
    inv = (await _invite(client, pid, owner["actor_id"], f"@{bob['username']}")).json()

    # Owner revokes → 204; both the project list and Bob's inbox drop it.
    r = await client.delete(
        f"/api/v1/projects/{pid}/invitations/{inv['id']}", headers=_headers(owner["actor_id"])
    )
    assert r.status_code == 204, r.text
    assert (
        await client.get(f"/api/v1/projects/{pid}/invitations", headers=_headers(owner["actor_id"]))
    ).json() == []
    assert (
        await client.get("/api/v1/me/invitations", headers=_headers(bob["actor_id"]))
    ).json() == []

    # Accepting a revoked invite is no longer possible → 409.
    r = await client.post(
        f"/api/v1/invitations/{inv['id']}/accept", headers=_headers(bob["actor_id"])
    )
    assert r.status_code == 409, r.text


async def test_non_member_cannot_invite_or_list(client: AsyncClient) -> None:
    owner = await _make_user(client, "Owner")
    stranger = await _make_user(client, "Stranger", email="stranger@example.com")
    project = await _create_project(client, owner["actor_id"], slug="manage-authz")
    pid = project["id"]

    # A signed-in non-member is 403'd by ensure_can_manage before the identifier is even resolved.
    r = await _invite(client, pid, stranger["actor_id"], "@whoever")
    assert r.status_code == 403, r.text
    r = await client.get(
        f"/api/v1/projects/{pid}/invitations", headers=_headers(stranger["actor_id"])
    )
    assert r.status_code == 403, r.text
