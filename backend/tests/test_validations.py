"""DB-backed tests for the 0.4.1 validation write path.

Covers: recording a validation against a claim / checkpoint / branch through the single
checkpoint chokepoint (one checkpoint, two refs, one ``validate`` contribution); the full
``ValidationOutcome`` matrix; the validation/target/project error cases; append-only ORM
enforcement on ``Validation``; and the enriched reads (actor, derived target, recording
checkpoint). These run only when a database is configured (see conftest.py); else they skip.
"""

from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import AppendOnlyError
from app.models.branch import Branch
from app.models.checkpoint import Checkpoint
from app.models.contribution import Contribution
from app.models.links import CheckpointRef
from app.models.validation import Validation

MISSING_ID = "00000000-0000-0000-0000-000000000000"
OUTCOMES = [
    "passed",
    "failed",
    "inconclusive",
    "needs_reproduction",
    "contradicts",
    "retract",
]


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


async def _checkpoint(client: AsyncClient, project_id: str, actor_id: str) -> str:
    resp = await client.post(
        f"/api/v1/projects/{project_id}/checkpoints",
        json={"summary": "a checkpoint to validate"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _validate(
    client: AsyncClient,
    project_id: str,
    actor_id: str,
    *,
    target_type: str,
    target_id: str,
    outcome: str = "passed",
    notes: str | None = None,
) -> tuple[int, dict]:
    resp = await client.post(
        f"/api/v1/projects/{project_id}/validations",
        json={
            "target_type": target_type,
            "target_id": target_id,
            "outcome": outcome,
            "notes": notes,
        },
        headers={"X-Dev-Actor-Id": actor_id},
    )
    return resp.status_code, (resp.json() if resp.content else {})


async def test_validate_claim_mints_checkpoint_with_refs_and_contribution(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client)
    thread_id = await _thread(client, project_id, actor_id)
    claim_id = await _claim(client, thread_id, actor_id)

    code, body = await _validate(
        client, project_id, actor_id,
        target_type="claim", target_id=claim_id, outcome="passed", notes="reproduced",
    )
    assert code == 201, body
    assert body["target_type"] == "claim"
    assert body["target_id"] == claim_id
    assert body["outcome"] == "passed"
    assert body["notes"] == "reproduced"
    assert body["actor"]["id"] == actor_id
    assert body["recording_checkpoint_id"] is not None
    validation_id = body["id"]
    recording_id = body["recording_checkpoint_id"]

    # Exactly one checkpoint exists (the minted one), scoped to the claim's thread, and it
    # carries both refs: validated->claim, recorded->validation.
    async with session_factory() as session:
        checkpoints = (await session.execute(select(Checkpoint))).scalars().all()
        assert len(checkpoints) == 1
        assert str(checkpoints[0].id) == recording_id
        assert str(checkpoints[0].thread_id) == thread_id  # claim-scoped (Decision #1 nicety)

        refs = (await session.execute(select(CheckpointRef))).scalars().all()
        ref_set = {(r.target_type, str(r.target_id), r.role) for r in refs}
        assert ("claim", claim_id, "validated") in ref_set
        assert ("validation", validation_id, "recorded") in ref_set

        # The contribution is a `validate` action linking the recording checkpoint.
        contribs = (await session.execute(select(Contribution))).scalars().all()
        validate_contribs = [c for c in contribs if c.action == "validate"]
        assert len(validate_contribs) == 1
        assert str(validate_contribs[0].checkpoint_id) == recording_id


async def test_validate_checkpoint_target(client: AsyncClient) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client)
    checkpoint_id = await _checkpoint(client, project_id, actor_id)

    code, body = await _validate(
        client, project_id, actor_id,
        target_type="checkpoint", target_id=checkpoint_id, outcome="inconclusive",
    )
    assert code == 201, body
    assert body["target_type"] == "checkpoint"
    assert body["target_id"] == checkpoint_id
    # The recording checkpoint is a *new* checkpoint, never the one being validated.
    assert body["recording_checkpoint_id"] is not None
    assert body["recording_checkpoint_id"] != checkpoint_id


async def test_validate_branch_target(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client)

    # Branches have no write path until 0.4.2; insert one directly to exercise the target.
    async with session_factory() as session:
        branch = Branch(project_id=UUID(project_id), name="alt-hypothesis")
        session.add(branch)
        await session.commit()
        branch_id = str(branch.id)

    code, body = await _validate(
        client, project_id, actor_id,
        target_type="branch", target_id=branch_id, outcome="contradicts",
    )
    assert code == 201, body
    assert body["target_type"] == "branch"
    assert body["target_id"] == branch_id
    assert body["recording_checkpoint_id"] is not None


async def test_all_outcomes_accepted_and_listed(client: AsyncClient) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client)
    thread_id = await _thread(client, project_id, actor_id)
    claim_id = await _claim(client, thread_id, actor_id)

    for outcome in OUTCOMES:
        code, body = await _validate(
            client, project_id, actor_id,
            target_type="claim", target_id=claim_id, outcome=outcome,
        )
        assert code == 201, f"{outcome}: {body}"

    # Both list views return every recorded validation.
    project_list = await client.get(f"/api/v1/projects/{project_id}/validations")
    assert project_list.status_code == 200
    assert {v["outcome"] for v in project_list.json()} == set(OUTCOMES)

    claim_list = await client.get(f"/api/v1/claims/{claim_id}/validations")
    assert claim_list.status_code == 200
    assert len(claim_list.json()) == len(OUTCOMES)
    assert all(v["recording_checkpoint_id"] is not None for v in claim_list.json())


async def test_validation_error_cases(client: AsyncClient) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client)
    other_project_id = await _project(client, slug="other-project")
    thread_id = await _thread(client, project_id, actor_id)
    claim_id = await _claim(client, thread_id, actor_id)

    # unknown outcome -> 422 (pydantic enum)
    code, _ = await _validate(
        client, project_id, actor_id,
        target_type="claim", target_id=claim_id, outcome="bogus",
    )
    assert code == 422

    # unknown target_type -> 422
    code, _ = await _validate(
        client, project_id, actor_id, target_type="widget", target_id=claim_id,
    )
    assert code == 422

    # missing target -> 404
    code, _ = await _validate(
        client, project_id, actor_id, target_type="claim", target_id=MISSING_ID,
    )
    assert code == 404

    # target belongs to a different project -> 400
    code, _ = await _validate(
        client, other_project_id, actor_id, target_type="claim", target_id=claim_id,
    )
    assert code == 400

    # missing project -> 404
    resp = await client.post(
        f"/api/v1/projects/{MISSING_ID}/validations",
        json={"target_type": "claim", "target_id": claim_id, "outcome": "passed"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert resp.status_code == 404

    # missing dev-actor header -> 400
    resp = await client.post(
        f"/api/v1/projects/{project_id}/validations",
        json={"target_type": "claim", "target_id": claim_id, "outcome": "passed"},
    )
    assert resp.status_code == 400


async def test_validation_is_append_only(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client)
    thread_id = await _thread(client, project_id, actor_id)
    claim_id = await _claim(client, thread_id, actor_id)
    code, body = await _validate(
        client, project_id, actor_id, target_type="claim", target_id=claim_id,
    )
    assert code == 201, body
    validation_id = body["id"]

    # Updating a validation is refused at the ORM layer.
    async with session_factory() as session:
        validation = await session.get(Validation, validation_id)
        assert validation is not None
        validation.notes = "amended"
        with pytest.raises(AppendOnlyError, match="append-only"):
            await session.flush()

    # Deleting a validation is refused at the ORM layer.
    async with session_factory() as session:
        validation = await session.get(Validation, validation_id)
        await session.delete(validation)
        with pytest.raises(AppendOnlyError):
            await session.flush()

    # It survived both rejected mutations.
    async with session_factory() as session:
        assert await session.get(Validation, validation_id) is not None
