"""DB-backed tests for the 0.4.2 branch write path.

Covers: forking a branch from a checkpoint (fork checkpoint stamped on the branch +
``create_branch`` contribution); branch-scoped vs main-line checkpoints; closing a branch
(status transition + ``close_branch`` checkpoint/contribution, already-closed rejected);
rejecting checkpoints on a closed branch; and the branch detail/list reads. These run only
when a database is configured (see conftest.py); else they skip.
"""

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.branch import Branch
from app.models.checkpoint import Checkpoint
from app.models.contribution import Contribution

MISSING_ID = "00000000-0000-0000-0000-000000000000"


async def _actor(client: AsyncClient) -> str:
    resp = await client.post("/api/v1/actors", json={"type": "human", "display_name": "Ada"})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _project(client: AsyncClient, slug: str = "test-project") -> str:
    resp = await client.post(
        "/api/v1/projects",
        json={"title": "Test Project", "slug": slug, "question": "What is X?"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _checkpoint(
    client: AsyncClient, project_id: str, actor_id: str, *, branch_id: str | None = None
) -> dict:
    body: dict = {"summary": "a checkpoint"}
    if branch_id is not None:
        body["branch_id"] = branch_id
    resp = await client.post(
        f"/api/v1/projects/{project_id}/checkpoints",
        json=body,
        headers={"X-Dev-Actor-Id": actor_id},
    )
    return {"status": resp.status_code, "body": resp.json() if resp.content else {}}


async def _branch(
    client: AsyncClient, project_id: str, actor_id: str, from_checkpoint: str
) -> dict:
    resp = await client.post(
        f"/api/v1/projects/{project_id}/branches",
        json={
            "from_checkpoint_id": from_checkpoint,
            "name": "alt-hypothesis",
            "reason": "explore a competing mechanism",
        },
        headers={"X-Dev-Actor-Id": actor_id},
    )
    return {"status": resp.status_code, "body": resp.json() if resp.content else {}}


async def test_fork_branch_from_checkpoint(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client)
    fork = (await _checkpoint(client, project_id, actor_id))["body"]
    fork_id = fork["id"]

    created = await _branch(client, project_id, actor_id, fork_id)
    assert created["status"] == 201, created["body"]
    branch = created["body"]
    assert branch["status"] == "open"
    assert branch["forked_from_checkpoint_id"] == fork_id
    branch_id = branch["id"]

    # The fork minted a checkpoint *on the branch*, parented on the fork point, and
    # recorded a create_branch contribution referencing the branch.
    async with session_factory() as session:
        on_branch = (
            (await session.execute(select(Checkpoint).where(Checkpoint.branch_id == branch_id)))
            .scalars()
            .all()
        )
        assert len(on_branch) == 1
        assert str(on_branch[0].id) != fork_id  # the fork point itself stays main-line

        contribs = (await session.execute(select(Contribution))).scalars().all()
        assert any(c.action == "create_branch" for c in contribs)

    # The branch detail read surfaces that first checkpoint.
    detail = await client.get(f"/api/v1/branches/{branch_id}")
    assert detail.status_code == 200
    assert len(detail.json()["checkpoints"]) == 1


async def test_branch_scoped_vs_main_line_checkpoints(client: AsyncClient) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client)
    fork = (await _checkpoint(client, project_id, actor_id))["body"]
    branch = (await _branch(client, project_id, actor_id, fork["id"]))["body"]
    branch_id = branch["id"]

    # A checkpoint with branch_id lands on the branch; one without stays main-line (None).
    on_branch = await _checkpoint(client, project_id, actor_id, branch_id=branch_id)
    assert on_branch["status"] == 201, on_branch["body"]
    assert on_branch["body"]["branch_id"] == branch_id

    main_line = await _checkpoint(client, project_id, actor_id)
    assert main_line["status"] == 201, main_line["body"]
    assert main_line["body"]["branch_id"] is None

    # Branch detail now shows the fork checkpoint + the branch-scoped one (not the main one).
    detail = await client.get(f"/api/v1/branches/{branch_id}")
    assert {c["id"] for c in detail.json()["checkpoints"]} == {
        c["id"]
        for c in detail.json()["checkpoints"]
        if c["branch_id"] == branch_id
    }
    assert len(detail.json()["checkpoints"]) == 2


async def test_close_branch_dead_end(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client)
    fork = (await _checkpoint(client, project_id, actor_id))["body"]
    branch = (await _branch(client, project_id, actor_id, fork["id"]))["body"]
    branch_id = branch["id"]

    closed = await client.post(
        f"/api/v1/branches/{branch_id}/close",
        json={"outcome": "dead_end", "reason": "mechanism ruled out by the data"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert closed.status_code == 200, closed.text
    assert closed.json()["status"] == "dead_end"

    # The close recorded a close_branch contribution; the status survived (not deleted).
    async with session_factory() as session:
        branch_row = await session.get(Branch, branch_id)
        assert branch_row is not None
        assert branch_row.status.value == "dead_end"
        contribs = (await session.execute(select(Contribution))).scalars().all()
        assert any(c.action == "close_branch" for c in contribs)

    # Closing an already-closed branch is rejected.
    again = await client.post(
        f"/api/v1/branches/{branch_id}/close",
        json={"outcome": "closed", "reason": "x"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert again.status_code == 400

    # No new checkpoints can be recorded on the closed branch.
    rejected = await _checkpoint(client, project_id, actor_id, branch_id=branch_id)
    assert rejected["status"] == 400


async def test_branch_error_cases(client: AsyncClient) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client)
    other_project_id = await _project(client, slug="other-project")
    fork = (await _checkpoint(client, project_id, actor_id))["body"]

    headers = {"X-Dev-Actor-Id": actor_id}

    # missing project
    r = await client.post(
        f"/api/v1/projects/{MISSING_ID}/branches",
        json={"from_checkpoint_id": fork["id"], "name": "b"},
        headers=headers,
    )
    assert r.status_code == 404

    # missing fork checkpoint
    r = await client.post(
        f"/api/v1/projects/{project_id}/branches",
        json={"from_checkpoint_id": MISSING_ID, "name": "b"},
        headers=headers,
    )
    assert r.status_code == 404

    # fork checkpoint from a different project
    r = await client.post(
        f"/api/v1/projects/{other_project_id}/branches",
        json={"from_checkpoint_id": fork["id"], "name": "b"},
        headers=headers,
    )
    assert r.status_code == 400

    # branch create requires the dev-actor header
    r = await client.post(
        f"/api/v1/projects/{project_id}/branches",
        json={"from_checkpoint_id": fork["id"], "name": "b"},
    )
    assert r.status_code == 400

    # invalid close outcome -> 422 (Literal)
    branch = (await _branch(client, project_id, actor_id, fork["id"]))["body"]
    r = await client.post(
        f"/api/v1/branches/{branch['id']}/close",
        json={"outcome": "merged", "reason": "x"},
        headers=headers,
    )
    assert r.status_code == 422

    # close a missing branch
    r = await client.post(
        f"/api/v1/branches/{MISSING_ID}/close",
        json={"outcome": "closed"},
        headers=headers,
    )
    assert r.status_code == 404
