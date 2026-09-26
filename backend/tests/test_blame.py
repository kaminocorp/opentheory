"""DB-backed tests for the 0.36.0 semantic research-git blame.

Covers: empty chain, asserted + author, validation signal move, instrument
grounding, unknown claim mints nothing, deterministic repeat, foreign-project
404. Skip when no database is configured (see conftest.py).
"""

from uuid import UUID

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.actor import Actor
from app.models.checkpoint import Checkpoint
from app.services.tool_runs import run_instrument
from app.toolbench.instruments import CALC_EVAL

MISSING_ID = "00000000-0000-0000-0000-000000000000"


async def _actor(client: AsyncClient) -> str:
    resp = await client.post("/api/v1/actors", json={"type": "human", "display_name": "Ada"})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _project(client: AsyncClient, slug: str = "blame-project") -> tuple[str, str]:
    actor_id = await _actor(client)
    resp = await client.post(
        "/api/v1/projects",
        json={"title": "Blame Project", "slug": slug, "question": "Who produced it?"},
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
    refs: list[dict] | None = None,
    parent_ids: list[str] | None = None,
) -> dict:
    body: dict = {"summary": summary}
    if thread_id is not None:
        body["thread_id"] = thread_id
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


async def _blame(client: AsyncClient, project_id: str, claim_id: str):
    return await client.get(f"/api/v1/projects/{project_id}/claims/{claim_id}/blame")


async def _count_checkpoints(session_factory: async_sessionmaker, project_id: str) -> int:
    async with session_factory() as session:
        result = await session.execute(
            select(func.count()).select_from(Checkpoint).where(Checkpoint.project_id == project_id)
        )
        return int(result.scalar_one())


async def test_empty_chain_when_claim_never_referenced(client: AsyncClient) -> None:
    project_id, actor_id = await _project(client, slug="empty-blame")
    thread_id = await _thread(client, project_id, actor_id)
    claim_id = await _claim(client, thread_id, actor_id)
    await _checkpoint(client, project_id, actor_id, summary="unrelated")

    resp = await _blame(client, project_id, claim_id)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["empty"] is True
    assert body["chain"] == []
    assert body["checkpoint_ids"] == []
    assert body["claim_id"] == claim_id
    assert body["current_signal"] == "none"
    assert body["current_grounding"] == "ungrounded"


async def test_asserted_checkpoint_carries_author(client: AsyncClient) -> None:
    project_id, actor_id = await _project(client, slug="asserted-blame")
    thread_id = await _thread(client, project_id, actor_id)
    claim_id = await _claim(client, thread_id, actor_id)
    tip = await _checkpoint(
        client,
        project_id,
        actor_id,
        summary="claim opened",
        thread_id=thread_id,
        refs=[{"target_type": "claim", "target_id": claim_id, "role": "asserted"}],
    )

    resp = await _blame(client, project_id, claim_id)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["empty"] is False
    assert body["checkpoint_ids"] == [tip["id"]]
    assert len(body["chain"]) == 1
    step = body["chain"][0]
    assert step["checkpoint_id"] == tip["id"]
    assert step["author"]["id"] == actor_id
    assert step["author"]["type"] == "human"
    assert step["author"]["display_name"] == "Ada"
    assert step["contribution_kind"] == "create_checkpoint"
    assert "asserted" in step["roles"]
    assert step["signal_moved"] is False
    assert step["grounding_moved"] is False


async def test_validation_step_moves_signal(client: AsyncClient) -> None:
    project_id, actor_id = await _project(client, slug="signal-blame")
    thread_id = await _thread(client, project_id, actor_id)
    claim_id = await _claim(client, thread_id, actor_id)
    opened = await _checkpoint(
        client,
        project_id,
        actor_id,
        summary="opened",
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

    resp = await _blame(client, project_id, claim_id)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["checkpoint_ids"] == [opened["id"], after_id]
    assert body["current_signal"] == "validated"
    last = body["chain"][-1]
    assert last["checkpoint_id"] == after_id
    assert last["contribution_kind"] == "validate"
    assert "validated" in last["roles"]
    assert last["signal_moved"] is True
    assert last["from_signal"] == "none"
    assert last["signal_after"] == "validated"


async def test_instrument_step_on_targeted_claim(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    project_id, actor_id = await _project(client, slug="instrument-blame")
    thread_id = await _thread(client, project_id, actor_id)
    claim_id = await _claim(client, thread_id, actor_id)
    async with session_factory() as session:
        actor = await session.get(Actor, UUID(actor_id))
        assert actor is not None
        result = await run_instrument(
            session,
            UUID(project_id),
            CALC_EVAL,
            actor,
            inputs={"expression": "1 + 1"},
            thread_id=UUID(thread_id),
            claim_id=UUID(claim_id),
            relation_kind="support",
        )
    after_id = str(result.checkpoint.id)

    resp = await _blame(client, project_id, claim_id)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["empty"] is False
    assert after_id in body["checkpoint_ids"]
    step = next(row for row in body["chain"] if row["checkpoint_id"] == after_id)
    assert "evidenced" in step["roles"]
    assert "instrument" in step["roles"]
    assert any(
        row["instrument"] == "calc.eval" and row["status"] == "result"
        for row in step["instruments"]
    )
    assert step["grounding_moved"] is True
    assert step["from_grounding"] == "ungrounded"
    assert step["grounding_after"] == "B"
    assert step["agent_run"] is None


async def test_unknown_claim_is_404_and_mints_nothing(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    project_id, actor_id = await _project(client, slug="unknown-blame")
    thread_id = await _thread(client, project_id, actor_id)
    await _claim(client, thread_id, actor_id)
    before = await _count_checkpoints(session_factory, project_id)

    missing = await _blame(client, project_id, MISSING_ID)
    assert missing.status_code == 404, missing.text
    assert "not found" in missing.json()["detail"].lower()

    after = await _count_checkpoints(session_factory, project_id)
    assert after == before


async def test_claim_in_other_project_is_404(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    project_a, actor_a = await _project(client, slug="blame-a")
    thread_a = await _thread(client, project_a, actor_a)
    claim_a = await _claim(client, thread_a, actor_a)
    project_b, _actor_b = await _project(client, slug="blame-b")
    before = await _count_checkpoints(session_factory, project_b)

    resp = await _blame(client, project_b, claim_a)
    assert resp.status_code == 404, resp.text
    after = await _count_checkpoints(session_factory, project_b)
    assert after == before


async def test_unknown_project_is_404(client: AsyncClient) -> None:
    project_id, actor_id = await _project(client, slug="blame-proj-404")
    thread_id = await _thread(client, project_id, actor_id)
    claim_id = await _claim(client, thread_id, actor_id)
    resp = await _blame(client, MISSING_ID, claim_id)
    assert resp.status_code == 404, resp.text


async def test_deterministic_repeat(client: AsyncClient) -> None:
    project_id, actor_id = await _project(client, slug="blame-deterministic")
    thread_id = await _thread(client, project_id, actor_id)
    claim_id = await _claim(client, thread_id, actor_id)
    await _checkpoint(
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

    first = await _blame(client, project_id, claim_id)
    second = await _blame(client, project_id, claim_id)
    assert first.status_code == 200 and second.status_code == 200
    assert first.json() == second.json()


async def test_unrelated_checkpoint_stays_off_the_chain(client: AsyncClient) -> None:
    project_id, actor_id = await _project(client, slug="blame-filter")
    thread_id = await _thread(client, project_id, actor_id)
    claim_id = await _claim(client, thread_id, actor_id)
    other = await _claim(client, thread_id, actor_id, statement="Y holds.")
    await _checkpoint(client, project_id, actor_id, summary="noise")
    mine = await _checkpoint(
        client,
        project_id,
        actor_id,
        summary="this claim",
        thread_id=thread_id,
        refs=[{"target_type": "claim", "target_id": claim_id, "role": "asserted"}],
    )
    await _checkpoint(
        client,
        project_id,
        actor_id,
        summary="other claim",
        thread_id=thread_id,
        refs=[{"target_type": "claim", "target_id": other, "role": "asserted"}],
    )

    resp = await _blame(client, project_id, claim_id)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["checkpoint_ids"] == [mine["id"]]
