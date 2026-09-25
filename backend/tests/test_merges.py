"""DB-backed tests for the 0.21.0 merge write path.

Covers: multi-parent merge of two open branches onto the main line; one branch
into main; closed/merged source rejected; merged line sealed against further
checkpoints; resolved-without-rationale refused; claim refs recorded without
rewriting the claim; already-merged not silently re-merged. These run only when
a database is configured (see conftest.py); else they skip.
"""

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.branch import Branch
from app.models.checkpoint import Checkpoint, checkpoint_parent
from app.models.claim import Claim
from app.models.contribution import Contribution

MISSING_ID = "00000000-0000-0000-0000-000000000000"


async def _actor(client: AsyncClient) -> str:
    resp = await client.post("/api/v1/actors", json={"type": "human", "display_name": "Ada"})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _project(client: AsyncClient, slug: str = "merge-project") -> str:
    actor = await client.post(
        "/api/v1/actors", json={"type": "human", "display_name": "Author"}
    )
    assert actor.status_code == 201, actor.text
    resp = await client.post(
        "/api/v1/projects",
        json={"title": "Merge Project", "slug": slug, "question": "What is X?"},
        headers={"X-Dev-Actor-Id": actor.json()["id"]},
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
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _branch(
    client: AsyncClient,
    project_id: str,
    actor_id: str,
    from_checkpoint: str,
    name: str = "alt-hypothesis",
) -> dict:
    resp = await client.post(
        f"/api/v1/projects/{project_id}/branches",
        json={"from_checkpoint_id": from_checkpoint, "name": name},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _thread(client: AsyncClient, project_id: str, actor_id: str) -> str:
    resp = await client.post(
        f"/api/v1/projects/{project_id}/threads",
        json={"title": "T", "question": "q?"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _claim(client: AsyncClient, thread_id: str, actor_id: str) -> str:
    resp = await client.post(
        f"/api/v1/threads/{thread_id}/claims",
        json={"kind": "hypothesis", "statement": "X is caused by Y."},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_merge_two_branches_is_multi_parent(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client)
    fork = await _checkpoint(client, project_id, actor_id)
    left = await _branch(client, project_id, actor_id, fork["id"], name="left")
    right = await _branch(client, project_id, actor_id, fork["id"], name="right")
    left_head = await _checkpoint(client, project_id, actor_id, branch_id=left["id"])
    right_head = await _checkpoint(client, project_id, actor_id, branch_id=right["id"])

    merged = await client.post(
        f"/api/v1/projects/{project_id}/merges",
        json={
            "source_branch_ids": [left["id"], right["id"]],
            "resolution": "clean",
            "summary": "Both lines agree",
        },
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert merged.status_code == 201, merged.text
    body = merged.json()
    parent_ids = set(body["parent_ids"])
    assert left_head["id"] in parent_ids
    assert right_head["id"] in parent_ids
    assert fork["id"] in parent_ids  # main-line tip is also a parent
    assert len(parent_ids) >= 3
    assert body["checkpoint"]["branch_id"] is None
    assert body["checkpoint"]["contribution_kind"] == "merge"
    assert {b["status"] for b in body["source_branches"]} == {"merged"}
    branch_roles = {
        ref["role"] for ref in body["checkpoint"]["refs"] if ref["target_type"] == "branch"
    }
    assert branch_roles == {"merged"}

    async with session_factory() as session:
        left_row = await session.get(Branch, left["id"])
        right_row = await session.get(Branch, right["id"])
        assert left_row is not None and left_row.status.value == "merged"
        assert right_row is not None and right_row.status.value == "merged"
        contribs = (await session.execute(select(Contribution))).scalars().all()
        assert any(c.action == "merge" for c in contribs)
        edges = (
            await session.execute(
                select(checkpoint_parent.c.parent_id).where(
                    checkpoint_parent.c.checkpoint_id == body["checkpoint"]["id"]
                )
            )
        ).all()
        assert {str(parent_id) for (parent_id,) in edges} == parent_ids

    # Sealed: no new checkpoints on a merged line; history is not rewritten.
    rejected = await client.post(
        f"/api/v1/projects/{project_id}/checkpoints",
        json={"summary": "after merge", "branch_id": left["id"]},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert rejected.status_code == 400

    # Source checkpoints still exist with their original summaries.
    async with session_factory() as session:
        still_left = await session.get(Checkpoint, left_head["id"])
        assert still_left is not None
        assert still_left.summary == "a checkpoint"


async def test_merge_one_branch_into_main(client: AsyncClient) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client, slug="merge-into-main")
    fork = await _checkpoint(client, project_id, actor_id)
    branch = await _branch(client, project_id, actor_id, fork["id"])
    head = await _checkpoint(client, project_id, actor_id, branch_id=branch["id"])

    merged = await client.post(
        f"/api/v1/projects/{project_id}/merges",
        json={"source_branch_ids": [branch["id"]], "resolution": "clean"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert merged.status_code == 201, merged.text
    parents = set(merged.json()["parent_ids"])
    assert head["id"] in parents
    assert fork["id"] in parents
    assert len(parents) == 2
    assert merged.json()["source_branches"][0]["status"] == "merged"


async def test_merge_records_claims_without_rewriting_them(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client, slug="merge-claims")
    thread_id = await _thread(client, project_id, actor_id)
    claim_id = await _claim(client, thread_id, actor_id)
    fork = await _checkpoint(client, project_id, actor_id)
    left = await _branch(client, project_id, actor_id, fork["id"], name="a")
    right = await _branch(client, project_id, actor_id, fork["id"], name="b")

    merged = await client.post(
        f"/api/v1/projects/{project_id}/merges",
        json={
            "source_branch_ids": [left["id"], right["id"]],
            "resolution": "resolved",
            "rationale": "Keep the left statement; the right is a special case.",
            "claim_ids": [claim_id],
        },
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert merged.status_code == 201, merged.text
    claim_refs = [
        ref
        for ref in merged.json()["checkpoint"]["refs"]
        if ref["target_type"] == "claim"
    ]
    assert len(claim_refs) == 1
    assert claim_refs[0]["target_id"] == claim_id
    assert claim_refs[0]["role"] == "merged"
    assert merged.json()["checkpoint"]["content"]["rationale"]

    async with session_factory() as session:
        claim = await session.get(Claim, claim_id)
        assert claim is not None
        assert claim.statement == "X is caused by Y."


async def test_merge_rejects_closed_and_already_merged(client: AsyncClient) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client, slug="merge-closed")
    fork = await _checkpoint(client, project_id, actor_id)
    dead = await _branch(client, project_id, actor_id, fork["id"], name="dead")
    live = await _branch(client, project_id, actor_id, fork["id"], name="live")
    await client.post(
        f"/api/v1/branches/{dead['id']}/close",
        json={"outcome": "dead_end", "reason": "ruled out"},
        headers={"X-Dev-Actor-Id": actor_id},
    )

    closed = await client.post(
        f"/api/v1/projects/{project_id}/merges",
        json={"source_branch_ids": [dead["id"], live["id"]], "resolution": "clean"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert closed.status_code == 400

    first = await client.post(
        f"/api/v1/projects/{project_id}/merges",
        json={"source_branch_ids": [live["id"]], "resolution": "clean"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert first.status_code == 201, first.text

    again = await client.post(
        f"/api/v1/projects/{project_id}/merges",
        json={"source_branch_ids": [live["id"]], "resolution": "clean"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert again.status_code == 400


async def test_merge_error_cases(client: AsyncClient) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client, slug="merge-errors")
    other = await _project(client, slug="merge-other")
    fork = await _checkpoint(client, project_id, actor_id)
    branch = await _branch(client, project_id, actor_id, fork["id"])
    headers = {"X-Dev-Actor-Id": actor_id}

    r = await client.post(
        f"/api/v1/projects/{MISSING_ID}/merges",
        json={"source_branch_ids": [branch["id"]], "resolution": "clean"},
        headers=headers,
    )
    assert r.status_code == 404

    r = await client.post(
        f"/api/v1/projects/{project_id}/merges",
        json={"source_branch_ids": [MISSING_ID], "resolution": "clean"},
        headers=headers,
    )
    assert r.status_code == 404

    r = await client.post(
        f"/api/v1/projects/{other}/merges",
        json={"source_branch_ids": [branch["id"]], "resolution": "clean"},
        headers=headers,
    )
    assert r.status_code == 400

    r = await client.post(
        f"/api/v1/projects/{project_id}/merges",
        json={
            "source_branch_ids": [branch["id"]],
            "target_branch_id": branch["id"],
            "resolution": "clean",
        },
        headers=headers,
    )
    assert r.status_code == 400

    r = await client.post(
        f"/api/v1/projects/{project_id}/merges",
        json={"source_branch_ids": [branch["id"]], "resolution": "clean"},
    )
    assert r.status_code == 400

    r = await client.post(
        f"/api/v1/projects/{project_id}/merges",
        json={"source_branch_ids": [branch["id"]], "resolution": "resolved"},
        headers=headers,
    )
    assert r.status_code == 422
