"""DB-backed tests for the 0.21.0 tag write path.

Covers: create + list; uniqueness (no silent overwrite); append-only ORM guard;
cross-project / missing checkpoint rejected; tagging a sealed/merged line still
records (on the main line). These run only when a database is configured
(see conftest.py); else they skip.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import AppendOnlyError
from app.models.contribution import Contribution
from app.models.tag import Tag

MISSING_ID = "00000000-0000-0000-0000-000000000000"


async def _actor(client: AsyncClient) -> str:
    from tests.principals import make_dev_principal

    return await make_dev_principal(client)


async def _project(
    client: AsyncClient, slug: str = "tag-project", actor_id: str | None = None
) -> str:
    from tests.principals import create_owned_project, make_dev_principal

    if actor_id is None:
        actor_id = await make_dev_principal(client, display_name="Author")
    return await create_owned_project(client, actor_id, slug)


async def _checkpoint(client: AsyncClient, project_id: str, actor_id: str) -> dict:
    resp = await client.post(
        f"/api/v1/projects/{project_id}/checkpoints",
        json={"summary": "a result"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_create_and_list_tags(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client, actor_id=actor_id)
    checkpoint = await _checkpoint(client, project_id, actor_id)

    created = await client.post(
        f"/api/v1/projects/{project_id}/tags",
        json={
            "checkpoint_id": checkpoint["id"],
            "name": "validated-v1",
            "kind": "validated",
            "notes": "first established result",
        },
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert created.status_code == 201, created.text
    tag = created.json()
    assert tag["name"] == "validated-v1"
    assert tag["kind"] == "validated"
    assert tag["checkpoint_id"] == checkpoint["id"]
    assert tag["recording_checkpoint_id"] is not None
    assert tag["author"]["id"] == actor_id

    listed = await client.get(f"/api/v1/projects/{project_id}/tags")
    assert listed.status_code == 200
    assert [row["name"] for row in listed.json()] == ["validated-v1"]

    detail = await client.get(f"/api/v1/tags/{tag['id']}")
    assert detail.status_code == 200
    assert detail.json()["id"] == tag["id"]

    # The tagged checkpoint is unchanged (a pointer, not a rewrite).
    original = await client.get(f"/api/v1/checkpoints/{checkpoint['id']}")
    assert original.status_code == 200
    assert original.json()["summary"] == "a result"

    async with session_factory() as session:
        contribs = (await session.execute(select(Contribution))).scalars().all()
        assert any(c.action == "tag" for c in contribs)


async def test_duplicate_tag_name_is_conflict_not_overwrite(client: AsyncClient) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client, slug="tag-dup", actor_id=actor_id)
    first = await _checkpoint(client, project_id, actor_id)
    second = await _checkpoint(client, project_id, actor_id)

    ok = await client.post(
        f"/api/v1/projects/{project_id}/tags",
        json={"checkpoint_id": first["id"], "name": "v1", "kind": "milestone"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert ok.status_code == 201, ok.text

    clash = await client.post(
        f"/api/v1/projects/{project_id}/tags",
        json={"checkpoint_id": second["id"], "name": "v1", "kind": "validated"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert clash.status_code == 409

    listed = await client.get(f"/api/v1/projects/{project_id}/tags")
    names = [row["name"] for row in listed.json()]
    assert names.count("v1") == 1
    assert listed.json()[0]["checkpoint_id"] == first["id"]
    assert listed.json()[0]["kind"] == "milestone"


async def test_tag_is_append_only(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client, slug="tag-append", actor_id=actor_id)
    checkpoint = await _checkpoint(client, project_id, actor_id)
    created = await client.post(
        f"/api/v1/projects/{project_id}/tags",
        json={"checkpoint_id": checkpoint["id"], "name": "keep", "kind": "milestone"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert created.status_code == 201, created.text
    tag_id = created.json()["id"]

    async with session_factory() as session:
        tag = await session.get(Tag, tag_id)
        assert tag is not None
        tag.notes = "rewritten"
        with pytest.raises(AppendOnlyError, match="append-only"):
            await session.flush()
        await session.rollback()

    async with session_factory() as session:
        tag = await session.get(Tag, tag_id)
        assert tag is not None
        await session.delete(tag)
        with pytest.raises(AppendOnlyError):
            await session.flush()


async def test_list_tags_empty_existing_project_not_404(client: AsyncClient) -> None:
    """An existing project with no tags is `[]`, never a missing-route 404."""
    project_id = await _project(client, slug="tag-empty")
    listed = await client.get(f"/api/v1/projects/{project_id}/tags")
    assert listed.status_code == 200
    assert listed.json() == []

    missing = await client.get(f"/api/v1/projects/{MISSING_ID}/tags")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Project not found"


async def test_tag_error_cases(client: AsyncClient) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client, slug="tag-errors", actor_id=actor_id)
    other = await _project(client, slug="tag-other")
    checkpoint = await _checkpoint(client, project_id, actor_id)
    headers = {"X-Dev-Actor-Id": actor_id}

    r = await client.post(
        f"/api/v1/projects/{MISSING_ID}/tags",
        json={"checkpoint_id": checkpoint["id"], "name": "x", "kind": "milestone"},
        headers=headers,
    )
    assert r.status_code == 404

    r = await client.post(
        f"/api/v1/projects/{project_id}/tags",
        json={"checkpoint_id": MISSING_ID, "name": "x", "kind": "milestone"},
        headers=headers,
    )
    assert r.status_code == 404

    r = await client.post(
        f"/api/v1/projects/{other}/tags",
        json={"checkpoint_id": checkpoint["id"], "name": "x", "kind": "milestone"},
        headers=headers,
    )
    assert r.status_code == 403

    r = await client.post(
        f"/api/v1/projects/{project_id}/tags",
        json={"checkpoint_id": checkpoint["id"], "name": "x", "kind": "milestone"},
    )
    assert r.status_code == 400

    r = await client.get(f"/api/v1/tags/{MISSING_ID}")
    assert r.status_code == 404


async def test_tag_on_merged_branch_records_on_main_line(client: AsyncClient) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client, slug="tag-merged-line", actor_id=actor_id)
    fork = await client.post(
        f"/api/v1/projects/{project_id}/checkpoints",
        json={"summary": "root"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert fork.status_code == 201, fork.text
    branch = await client.post(
        f"/api/v1/projects/{project_id}/branches",
        json={"from_checkpoint_id": fork.json()["id"], "name": "alt"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert branch.status_code == 201, branch.text
    on_branch = await client.post(
        f"/api/v1/projects/{project_id}/checkpoints",
        json={"summary": "on alt", "branch_id": branch.json()["id"]},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert on_branch.status_code == 201, on_branch.text

    merged = await client.post(
        f"/api/v1/projects/{project_id}/merges",
        json={"source_branch_ids": [branch.json()["id"]], "resolution": "clean"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert merged.status_code == 201, merged.text

    tagged = await client.post(
        f"/api/v1/projects/{project_id}/tags",
        json={
            "checkpoint_id": on_branch.json()["id"],
            "name": "last-good",
            "kind": "retraction",
        },
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert tagged.status_code == 201, tagged.text
    recording = await client.get(
        f"/api/v1/checkpoints/{tagged.json()['recording_checkpoint_id']}"
    )
    assert recording.status_code == 200
    assert recording.json()["branch_id"] is None
