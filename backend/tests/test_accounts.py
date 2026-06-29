"""DB-backed tests for the account ``@username`` slice (0.8.3).

Covers: the bootstrap (``POST /accounts``) auto-generates a unique handle (from email local-part /
display name) and suffixes on collision; ``PATCH /me`` renames the caller's own handle (happy path,
``409`` on collision, ``422`` on invalid/reserved); ``resolve_account_by_identifier`` resolves by
``@username`` **and** email; and the public member-list ``AccountSummary`` exposes ``username`` but
never email/roles/external_id. These run only when a database is configured (``TEST_DATABASE_URL``).

Acting users are built the Account-owns-Actor way (an Account via ``POST /accounts`` + a linked
``human`` Actor via ``POST /actors``), then driven through the dev ``X-Dev-Actor-Id`` path.
"""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.services.account import resolve_account_by_identifier


async def _account_actor(
    client: AsyncClient,
    *,
    display_name: str,
    email: str | None = None,
    roles: tuple[str, ...] = (),
) -> tuple[str, str]:
    """Create an Account (+ optional email) and a linked human Actor; return (actor_id, account_id).

    Mirrors the ``internal_funder`` fixture but accepts an ``email`` so the PII-omission assertion
    can prove the member summary *drops* an email that actually exists on the account.
    """
    acct = await client.post(
        "/api/v1/accounts",
        json={"display_name": display_name, "email": email, "roles": list(roles)},
    )
    assert acct.status_code == 201, acct.text
    account_id = acct.json()["id"]
    actor = await client.post(
        "/api/v1/actors",
        json={"type": "human", "display_name": display_name, "account_id": account_id},
    )
    assert actor.status_code == 201, actor.text
    return actor.json()["id"], account_id


async def test_bootstrap_generates_unique_usernames(client: AsyncClient) -> None:
    a = await client.post("/api/v1/accounts", json={"display_name": "Ada Lovelace"})
    b = await client.post("/api/v1/accounts", json={"display_name": "Ada Lovelace"})
    assert a.status_code == 201 and b.status_code == 201
    assert a.json()["username"] == "ada_lovelace"
    assert b.json()["username"] == "ada_lovelace2"  # collision → sequential suffix


async def test_bootstrap_username_from_email_local_part(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/accounts",
        json={"display_name": "Anonymous", "email": "Grace.Hopper@navy.mil"},
    )
    assert r.status_code == 201, r.text
    # Email local-part wins over display name ("Anonymous" would normalize to a reserved word).
    assert r.json()["username"] == "grace_hopper"


async def test_me_rename_happy_path(client: AsyncClient) -> None:
    actor_id, _ = await _account_actor(client, display_name="Rename Me")
    headers = {"X-Dev-Actor-Id": actor_id}

    me = await client.get("/api/v1/me", headers=headers)
    assert me.status_code == 200, me.text
    assert me.json()["account"]["username"] == "rename_me"  # auto-generated on bootstrap

    resp = await client.patch("/api/v1/me", json={"username": "NewHandle"}, headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["account"]["username"] == "newhandle"  # normalized + persisted

    me2 = await client.get("/api/v1/me", headers=headers)
    assert me2.json()["account"]["username"] == "newhandle"


async def test_me_rename_noop_to_own_handle(client: AsyncClient) -> None:
    # Renaming to one's *current* handle is a no-op success (not a self-collision 409).
    actor_id, _ = await _account_actor(client, display_name="Same")
    headers = {"X-Dev-Actor-Id": actor_id}
    current = (await client.get("/api/v1/me", headers=headers)).json()["account"]["username"]
    resp = await client.patch("/api/v1/me", json={"username": current}, headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["account"]["username"] == current


async def test_me_rename_collision_409(client: AsyncClient) -> None:
    a_actor, _ = await _account_actor(client, display_name="Alice")
    b_actor, _ = await _account_actor(client, display_name="Bob")
    a_handle = (await client.get("/api/v1/me", headers={"X-Dev-Actor-Id": a_actor})).json()[
        "account"
    ]["username"]

    resp = await client.patch(
        "/api/v1/me", json={"username": a_handle}, headers={"X-Dev-Actor-Id": b_actor}
    )
    assert resp.status_code == 409, resp.text


async def test_me_rename_invalid_422(client: AsyncClient) -> None:
    actor_id, _ = await _account_actor(client, display_name="Carol")
    headers = {"X-Dev-Actor-Id": actor_id}
    for bad in ["ab", "admin", "no spaces", "a" * 31]:
        resp = await client.patch("/api/v1/me", json={"username": bad}, headers=headers)
        assert resp.status_code == 422, (bad, resp.text)


async def test_resolve_account_by_identifier(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    await client.post(
        "/api/v1/accounts",
        json={"display_name": "Finder", "email": "Find.Me@example.com"},
    )
    async with session_factory() as session:
        by_handle = await resolve_account_by_identifier(session, "@find_me")
        assert by_handle is not None and by_handle.username == "find_me"
        # Email match is case-insensitive.
        by_email = await resolve_account_by_identifier(session, "find.me@EXAMPLE.com")
        assert by_email is not None and by_email.id == by_handle.id
        assert await resolve_account_by_identifier(session, "@nobody_here") is None
        assert await resolve_account_by_identifier(session, "") is None


async def test_member_summary_exposes_username_not_pii(client: AsyncClient) -> None:
    owner_actor, _ = await _account_actor(
        client, display_name="Owner", email="owner@secret.example", roles=("internal",)
    )
    proj = await client.post(
        "/api/v1/projects",
        json={"title": "P", "slug": "members-pii", "question": "Q?"},
        headers={"X-Dev-Actor-Id": owner_actor},
    )
    assert proj.status_code == 201, proj.text

    members = await client.get(f"/api/v1/projects/{proj.json()['id']}/members")
    assert members.status_code == 200, members.text
    data = members.json()
    assert len(data) == 1
    account = data[0]["account"]
    assert account["username"]  # public handle present
    # PII never leaks through the public member summary.
    assert "email" not in account
    assert "roles" not in account
    assert "external_id" not in account
