"""DB-backed tests for the 0.3.2 checkpoint service, append-only, and contributions.

Covers checkpoint creation with parent linkage and refs, list/detail reads, append-only
ORM enforcement on Checkpoint and CheckpointRef, validation of project/thread/parent/ref
context, and Contribution auto-recording for all four create flows. These run only when
a database is configured (see conftest.py); otherwise they skip.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import AppendOnlyError
from app.models.checkpoint import Checkpoint
from app.models.contribution import Contribution
from app.models.links import CheckpointRef
from app.models.thread import Thread

MISSING_ID = "00000000-0000-0000-0000-000000000000"


async def _actor(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/actors", json={"type": "human", "display_name": "Ada"}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _project(client: AsyncClient, slug: str = "test-project") -> str:
    resp = await client.post(
        "/api/v1/projects",
        json={"title": "Test Project", "slug": slug, "question": "What is X?"},
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


async def _claim(client: AsyncClient, thread_id: str, actor_id: str) -> str:
    resp = await client.post(
        f"/api/v1/threads/{thread_id}/claims",
        json={"kind": "hypothesis", "statement": "X is caused by Y."},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _evidence(client: AsyncClient, claim_id: str, actor_id: str) -> str:
    resp = await client.post(
        f"/api/v1/claims/{claim_id}/evidence",
        json={"title": "Smith 2024", "source_type": "paper", "relation_kind": "support"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_create_checkpoint_with_refs_and_parent(client: AsyncClient) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client)
    thread_id = await _thread(client, project_id, actor_id)
    claim_id = await _claim(client, thread_id, actor_id)
    evidence_id = await _evidence(client, claim_id, actor_id)

    # root checkpoint (no parents)
    root = await client.post(
        f"/api/v1/projects/{project_id}/checkpoints",
        json={
            "thread_id": thread_id,
            "summary": "Opened the thread",
            "stage": "decompose",
            "content": {"note": "first move"},
            "refs": [{"target_type": "thread", "target_id": thread_id, "role": "opened"}],
        },
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert root.status_code == 201, root.text
    root_body = root.json()
    assert root_body["author_id"] == actor_id
    assert root_body["stage"] == "decompose"
    assert root_body["content"] == {"note": "first move"}
    assert root_body["parent_ids"] == []
    assert {r["target_type"] for r in root_body["refs"]} == {"thread"}
    root_id = root_body["id"]

    # child checkpoint referencing the claim + evidence, with the root as parent
    child = await client.post(
        f"/api/v1/projects/{project_id}/checkpoints",
        json={
            "thread_id": thread_id,
            "summary": "Recorded a claim with supporting evidence",
            "parent_ids": [root_id],
            "refs": [
                {"target_type": "claim", "target_id": claim_id, "role": "asserted"},
                {"target_type": "evidence", "target_id": evidence_id, "role": "cited"},
            ],
        },
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert child.status_code == 201, child.text
    child_body = child.json()
    assert child_body["parent_ids"] == [root_id]
    assert {r["target_type"] for r in child_body["refs"]} == {"claim", "evidence"}

    # detail + list round-trip
    detail = await client.get(f"/api/v1/checkpoints/{child_body['id']}")
    assert detail.status_code == 200
    assert detail.json()["parent_ids"] == [root_id]

    listed = await client.get(f"/api/v1/projects/{project_id}/checkpoints")
    assert listed.status_code == 200
    assert {c["id"] for c in listed.json()} == {root_id, child_body["id"]}


async def test_duplicate_parent_ids_are_deduplicated(client: AsyncClient) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client)
    root = await client.post(
        f"/api/v1/projects/{project_id}/checkpoints",
        json={"summary": "root"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert root.status_code == 201, root.text
    root_id = root.json()["id"]

    # the same parent listed twice collapses to a single link (redundant edge)
    child = await client.post(
        f"/api/v1/projects/{project_id}/checkpoints",
        json={"summary": "child", "parent_ids": [root_id, root_id]},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert child.status_code == 201, child.text
    assert child.json()["parent_ids"] == [root_id]


async def test_checkpoint_stage_optional(client: AsyncClient) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client)
    resp = await client.post(
        f"/api/v1/projects/{project_id}/checkpoints",
        json={"summary": "A stageless checkpoint"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["stage"] is None
    assert resp.json()["thread_id"] is None


async def test_checkpoint_requires_dev_actor_header(client: AsyncClient) -> None:
    project_id = await _project(client)
    resp = await client.post(
        f"/api/v1/projects/{project_id}/checkpoints",
        json={"summary": "no actor"},
    )
    assert resp.status_code == 400


async def test_checkpoint_validation_errors(client: AsyncClient) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client)
    other_project_id = await _project(client, slug="other-project")
    thread_id = await _thread(client, project_id, actor_id)
    claim_id = await _claim(client, thread_id, actor_id)

    headers = {"X-Dev-Actor-Id": actor_id}

    # missing project
    r = await client.post(
        f"/api/v1/projects/{MISSING_ID}/checkpoints",
        json={"summary": "s"},
        headers=headers,
    )
    assert r.status_code == 404

    # unknown target_type
    r = await client.post(
        f"/api/v1/projects/{project_id}/checkpoints",
        json={
            "summary": "s",
            "refs": [{"target_type": "widget", "target_id": claim_id, "role": "x"}],
        },
        headers=headers,
    )
    assert r.status_code == 422

    # ref target does not exist
    r = await client.post(
        f"/api/v1/projects/{project_id}/checkpoints",
        json={
            "summary": "s",
            "refs": [{"target_type": "claim", "target_id": MISSING_ID, "role": "x"}],
        },
        headers=headers,
    )
    assert r.status_code == 404

    # ref target belongs to a different project
    r = await client.post(
        f"/api/v1/projects/{other_project_id}/checkpoints",
        json={
            "summary": "s",
            "refs": [{"target_type": "claim", "target_id": claim_id, "role": "x"}],
        },
        headers=headers,
    )
    assert r.status_code == 400

    # parent does not exist
    r = await client.post(
        f"/api/v1/projects/{project_id}/checkpoints",
        json={"summary": "s", "parent_ids": [MISSING_ID]},
        headers=headers,
    )
    assert r.status_code == 404

    # thread from a different project
    r = await client.post(
        f"/api/v1/projects/{other_project_id}/checkpoints",
        json={"summary": "s", "thread_id": thread_id},
        headers=headers,
    )
    assert r.status_code == 400


async def test_checkpoint_is_append_only(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client)
    created = await client.post(
        f"/api/v1/projects/{project_id}/checkpoints",
        json={
            "summary": "immutable",
            "refs": [],
        },
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    checkpoint_id = body["id"]
    # empty refs round-trips as an empty list (and writes no CheckpointRef rows, asserted below)
    assert body["refs"] == []

    # Updating a checkpoint is refused at the ORM layer, with an identifying message.
    async with session_factory() as session:
        checkpoint = await session.get(Checkpoint, checkpoint_id)
        assert checkpoint is not None
        checkpoint.summary = "mutated"
        with pytest.raises(AppendOnlyError, match="append-only"):
            await session.flush()

    # Deleting a checkpoint is refused at the ORM layer.
    async with session_factory() as session:
        checkpoint = await session.get(Checkpoint, checkpoint_id)
        await session.delete(checkpoint)
        with pytest.raises(AppendOnlyError):
            await session.flush()

    # The guard is selective: a non-append-only model (Thread) updates freely.
    thread_id = await _thread(client, project_id, actor_id)
    async with session_factory() as session:
        thread = await session.get(Thread, thread_id)
        thread.title = "renamed"
        await session.flush()  # must not raise
        await session.commit()

    # No CheckpointRef rows were created for the ref-less checkpoint.
    async with session_factory() as session:
        refs = (
            (await session.execute(select(CheckpointRef))).scalars().all()
        )
        assert refs == []

    # The checkpoint and its create-contribution survived the rejected mutations.
    async with session_factory() as session:
        assert await session.get(Checkpoint, checkpoint_id) is not None
        contribs = (await session.execute(select(Contribution))).scalars().all()
        kinds = {c.action for c in contribs}
        assert "create_checkpoint" in kinds


async def test_checkpoint_ref_is_append_only(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client)
    thread_id = await _thread(client, project_id, actor_id)
    created = await client.post(
        f"/api/v1/projects/{project_id}/checkpoints",
        json={
            "summary": "with a ref",
            "refs": [{"target_type": "thread", "target_id": thread_id, "role": "opened"}],
        },
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert created.status_code == 201, created.text

    async with session_factory() as session:
        ref = (await session.execute(select(CheckpointRef))).scalars().first()
        assert ref is not None
        ref.role = "changed"
        with pytest.raises(AppendOnlyError):
            await session.flush()

    async with session_factory() as session:
        ref = (await session.execute(select(CheckpointRef))).scalars().first()
        await session.delete(ref)
        with pytest.raises(AppendOnlyError):
            await session.flush()


async def test_contribution_recorded_for_all_create_flows(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client)
    thread_id = await _thread(client, project_id, actor_id)
    claim_id = await _claim(client, thread_id, actor_id)
    await _evidence(client, claim_id, actor_id)
    await client.post(
        f"/api/v1/projects/{project_id}/checkpoints",
        json={"summary": "a checkpoint"},
        headers={"X-Dev-Actor-Id": actor_id},
    )

    async with session_factory() as session:
        rows = (await session.execute(select(Contribution))).scalars().all()

    by_action = {r.action for r in rows}
    assert by_action == {
        "create_thread",
        "create_claim",
        "create_evidence",
        "create_checkpoint",
    }
    # every contribution attributes the acting actor and the project
    assert all(str(r.actor_id) == actor_id for r in rows)
    assert all(str(r.project_id) == project_id for r in rows)
    # the checkpoint contribution links the checkpoint it recorded
    checkpoint_contrib = next(r for r in rows if r.action == "create_checkpoint")
    assert checkpoint_contrib.checkpoint_id is not None
    assert checkpoint_contrib.target_id == checkpoint_contrib.checkpoint_id
