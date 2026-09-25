"""DB-backed tests for the 0.29.0 semantic research-git diff.

Covers: empty delta, claim signal change, grounding move, unknown ref mints
nothing, deterministic repeat, branch/tag resolution, reverse direction.
Skip when no database is configured (see conftest.py).
"""

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.checkpoint import Checkpoint

MISSING_ID = "00000000-0000-0000-0000-000000000000"


async def _actor(client: AsyncClient) -> str:
    resp = await client.post("/api/v1/actors", json={"type": "human", "display_name": "Ada"})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _project(client: AsyncClient, slug: str = "diff-project") -> tuple[str, str]:
    actor_id = await _actor(client)
    resp = await client.post(
        "/api/v1/projects",
        json={"title": "Diff Project", "slug": slug, "question": "What moved?"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"], actor_id


async def _thread(client: AsyncClient, project_id: str, actor_id: str) -> str:
    resp = await client.post(
        f"/api/v1/projects/{project_id}/threads",
        json={"title": "T", "question": "q?"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _claim(
    client: AsyncClient, thread_id: str, actor_id: str, statement: str = "X holds."
) -> str:
    resp = await client.post(
        f"/api/v1/threads/{thread_id}/claims",
        json={"kind": "hypothesis", "statement": statement},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _checkpoint(
    client: AsyncClient,
    project_id: str,
    actor_id: str,
    *,
    summary: str = "a checkpoint",
    thread_id: str | None = None,
    branch_id: str | None = None,
    refs: list[dict] | None = None,
    parent_ids: list[str] | None = None,
) -> dict:
    body: dict = {"summary": summary}
    if thread_id is not None:
        body["thread_id"] = thread_id
    if branch_id is not None:
        body["branch_id"] = branch_id
    if refs is not None:
        body["refs"] = refs
    if parent_ids is not None:
        body["parent_ids"] = parent_ids
    resp = await client.post(
        f"/api/v1/projects/{project_id}/checkpoints",
        json=body,
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _diff(client: AsyncClient, project_id: str, from_ref: str, to_ref: str):
    return await client.get(
        f"/api/v1/projects/{project_id}/diff",
        params={"from": from_ref, "to": to_ref},
    )


async def _count_checkpoints(session_factory: async_sessionmaker, project_id: str) -> int:
    async with session_factory() as session:
        result = await session.execute(
            select(func.count()).select_from(Checkpoint).where(Checkpoint.project_id == project_id)
        )
        return int(result.scalar_one())


async def test_empty_delta_same_tip(client: AsyncClient) -> None:
    project_id, actor_id = await _project(client, slug="empty-same")
    tip = await _checkpoint(client, project_id, actor_id, summary="only")
    resp = await _diff(client, project_id, tip["id"], tip["id"])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["empty"] is True
    assert body["claims"] == []
    assert body["grounding"] == []
    assert body["instruments"] == []
    assert body["ancestry"]["diverged"] is False
    assert body["ancestry"]["interval_checkpoint_ids"] == []
    assert body["from_ref"]["checkpoint_id"] == tip["id"]
    assert body["to_ref"]["checkpoint_id"] == tip["id"]


async def test_empty_delta_two_idle_checkpoints(client: AsyncClient) -> None:
    project_id, actor_id = await _project(client, slug="empty-pair")
    first = await _checkpoint(client, project_id, actor_id, summary="before")
    second = await _checkpoint(
        client, project_id, actor_id, summary="after", parent_ids=[first["id"]]
    )
    resp = await _diff(client, project_id, first["id"], second["id"])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["empty"] is True
    assert body["claims"] == []
    assert body["grounding"] == []
    assert body["instruments"] == []
    assert body["ancestry"]["from_is_ancestor_of_to"] is True
    assert body["ancestry"]["interval_checkpoint_ids"] == [second["id"]]


async def test_claim_status_change(client: AsyncClient) -> None:
    project_id, actor_id = await _project(client, slug="status-change")
    thread_id = await _thread(client, project_id, actor_id)
    claim_id = await _claim(client, thread_id, actor_id)
    before = await _checkpoint(
        client,
        project_id,
        actor_id,
        summary="claim opened",
        thread_id=thread_id,
        refs=[{"target_type": "claim", "target_id": claim_id, "role": "asserted"}],
    )
    validated = await client.post(
        f"/api/v1/projects/{project_id}/validations",
        json={"target_type": "claim", "target_id": claim_id, "outcome": "passed"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert validated.status_code == 201, validated.text
    after_id = validated.json()["recording_checkpoint_id"]
    assert after_id

    resp = await _diff(client, project_id, before["id"], after_id)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["empty"] is False
    assert len(body["claims"]) == 1
    row = body["claims"][0]
    assert row["claim_id"] == claim_id
    assert row["change"] == "status_changed"
    assert row["from_signal"] == "none"
    assert row["to_signal"] == "validated"


async def test_grounding_move_via_hand_attached_evidence(client: AsyncClient) -> None:
    project_id, actor_id = await _project(client, slug="grounding-move")
    thread_id = await _thread(client, project_id, actor_id)
    claim_id = await _claim(client, thread_id, actor_id)
    before = await _checkpoint(
        client,
        project_id,
        actor_id,
        summary="ungrounded",
        thread_id=thread_id,
        refs=[{"target_type": "claim", "target_id": claim_id, "role": "asserted"}],
    )
    evidence = await client.post(
        f"/api/v1/claims/{claim_id}/evidence",
        json={"title": "a paper", "source_type": "paper", "relation_kind": "support"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert evidence.status_code == 201, evidence.text
    after = await _checkpoint(
        client,
        project_id,
        actor_id,
        summary="after attach",
        thread_id=thread_id,
        parent_ids=[before["id"]],
        refs=[{"target_type": "claim", "target_id": claim_id, "role": "asserted"}],
    )

    resp = await _diff(client, project_id, before["id"], after["id"])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["empty"] is False
    assert len(body["grounding"]) == 1
    move = body["grounding"][0]
    assert move["claim_id"] == claim_id
    assert move["from_headline"] == "ungrounded"
    assert move["to_headline"] == "D"
    assert move["movement"] == "raised"


async def test_unknown_ref_is_404_and_mints_nothing(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    project_id, actor_id = await _project(client, slug="unknown-ref")
    tip = await _checkpoint(client, project_id, actor_id)
    before = await _count_checkpoints(session_factory, project_id)

    missing = await _diff(client, project_id, MISSING_ID, tip["id"])
    assert missing.status_code == 404, missing.text
    assert "unknown ref" in missing.json()["detail"]

    gibberish = await _diff(client, project_id, tip["id"], "no-such-line")
    assert gibberish.status_code == 404, gibberish.text
    assert "unknown ref" in gibberish.json()["detail"]

    after = await _count_checkpoints(session_factory, project_id)
    assert after == before


async def test_deterministic_repeat(client: AsyncClient) -> None:
    project_id, actor_id = await _project(client, slug="deterministic")
    thread_id = await _thread(client, project_id, actor_id)
    claim_id = await _claim(client, thread_id, actor_id)
    before = await _checkpoint(
        client,
        project_id,
        actor_id,
        summary="open",
        thread_id=thread_id,
        refs=[{"target_type": "claim", "target_id": claim_id, "role": "asserted"}],
    )
    validated = await client.post(
        f"/api/v1/projects/{project_id}/validations",
        json={"target_type": "claim", "target_id": claim_id, "outcome": "passed"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert validated.status_code == 201, validated.text
    after_id = validated.json()["recording_checkpoint_id"]

    first = await _diff(client, project_id, before["id"], after_id)
    second = await _diff(client, project_id, before["id"], after_id)
    assert first.status_code == 200 and second.status_code == 200
    assert first.json() == second.json()


async def test_resolves_main_branch_and_tag_names(client: AsyncClient) -> None:
    project_id, actor_id = await _project(client, slug="resolve-names")
    root = await _checkpoint(client, project_id, actor_id, summary="root")
    branch = await client.post(
        f"/api/v1/projects/{project_id}/branches",
        json={"from_checkpoint_id": root["id"], "name": "alt"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert branch.status_code == 201, branch.text
    branch_id = branch.json()["id"]
    head = await _checkpoint(
        client, project_id, actor_id, summary="on alt", branch_id=branch_id
    )
    tagged = await client.post(
        f"/api/v1/projects/{project_id}/tags",
        json={"checkpoint_id": root["id"], "name": "v1", "kind": "milestone"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert tagged.status_code == 201, tagged.text

    by_main = await _diff(client, project_id, "main", "alt")
    assert by_main.status_code == 200, by_main.text
    # Tagging records a checkpoint on the main line, so ``main`` is that
    # recording tip — not ``root``. The named tag still points at ``root``.
    by_tag = await _diff(client, project_id, "v1", branch_id)
    assert by_tag.status_code == 200, by_tag.text
    assert by_tag.json()["from_ref"]["kind"] == "tag"
    assert by_tag.json()["from_ref"]["checkpoint_id"] == root["id"]
    assert by_tag.json()["to_ref"]["kind"] == "branch"
    assert by_tag.json()["to_ref"]["checkpoint_id"] == head["id"]

    by_main_body = by_main.json()
    assert by_main_body["from_ref"]["kind"] == "main"
    assert by_main_body["to_ref"]["kind"] == "branch"
    assert by_main_body["to_ref"]["checkpoint_id"] == head["id"]


async def test_instrument_outcome_between_tips(client: AsyncClient) -> None:
    project_id, actor_id = await _project(client, slug="instrument-delta")
    thread_id = await _thread(client, project_id, actor_id)
    before = await _checkpoint(client, project_id, actor_id, summary="before run", thread_id=thread_id)
    run = await client.post(
        f"/api/v1/projects/{project_id}/instruments/calc.eval/run",
        json={"inputs": {"expression": "1 + 1"}, "thread_id": thread_id},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert run.status_code == 201, run.text
    after_id = run.json()["checkpoint"]["id"]
    resp = await _diff(client, project_id, before["id"], after_id)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["empty"] is False
    assert any(
        row["instrument"] == "calc.eval" and row["status"] == "result"
        for row in body["instruments"]
    )


async def test_reverse_direction_inverts_status_change(client: AsyncClient) -> None:
    project_id, actor_id = await _project(client, slug="reverse")
    thread_id = await _thread(client, project_id, actor_id)
    claim_id = await _claim(client, thread_id, actor_id)
    before = await _checkpoint(
        client,
        project_id,
        actor_id,
        summary="open",
        thread_id=thread_id,
        refs=[{"target_type": "claim", "target_id": claim_id, "role": "asserted"}],
    )
    validated = await client.post(
        f"/api/v1/projects/{project_id}/validations",
        json={"target_type": "claim", "target_id": claim_id, "outcome": "passed"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert validated.status_code == 201, validated.text
    after_id = validated.json()["recording_checkpoint_id"]

    forward = (await _diff(client, project_id, before["id"], after_id)).json()
    reverse = (await _diff(client, project_id, after_id, before["id"])).json()
    assert forward["claims"][0]["change"] == "status_changed"
    assert reverse["claims"][0]["from_signal"] == "validated"
    assert reverse["claims"][0]["to_signal"] == "none"
