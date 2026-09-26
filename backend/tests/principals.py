"""Shared Account-backed principals for membership-gated write tests.

``ensure_is_member`` 403s account-less actors. Production writes always have an
Account (JWT → Account → human Actor). Tests that POST ledger writes must do
the same: create an Account, link a human Actor, then create the project as that
actor so they become OWNER.
"""

from httpx import AsyncClient


async def make_dev_principal(
    client: AsyncClient,
    *,
    display_name: str = "Ada",
    roles: tuple[str, ...] = (),
) -> str:
    """Return an actor id usable as ``X-Dev-Actor-Id`` whose account can hold membership."""
    acct = await client.post(
        "/api/v1/accounts", json={"display_name": display_name, "roles": list(roles)}
    )
    assert acct.status_code == 201, acct.text
    actor = await client.post(
        "/api/v1/actors",
        json={
            "type": "human",
            "display_name": display_name,
            "account_id": acct.json()["id"],
        },
    )
    assert actor.status_code == 201, actor.text
    return actor.json()["id"]


async def create_owned_project(
    client: AsyncClient,
    actor_id: str,
    slug: str,
    *,
    title: str = "Test Project",
    question: str = "What is X?",
) -> str:
    resp = await client.post(
        "/api/v1/projects",
        json={"title": title, "slug": slug, "question": question},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]
