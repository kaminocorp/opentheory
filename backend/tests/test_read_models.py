"""DB-backed tests for the 0.3.4 enriched read models.

Covers the project overview aggregate counts, the per-thread claim count on the thread
list, and the enriched checkpoint read (creating actor, contribution kind, and
referenced claim/evidence labels). Skip when no database is configured (see conftest.py).
"""

from httpx import AsyncClient


async def _actor(client: AsyncClient, name: str = "Ada") -> str:
    resp = await client.post("/api/v1/actors", json={"type": "human", "display_name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _project(client: AsyncClient, slug: str = "test-project") -> str:
    # Project creation now requires an acting actor; bootstrap a dev actor for the header.
    actor = await client.post(
        "/api/v1/actors", json={"type": "human", "display_name": "Author"}
    )
    assert actor.status_code == 201, actor.text
    resp = await client.post(
        "/api/v1/projects",
        json={"title": "Test Project", "slug": slug, "question": "What is X?"},
        headers={"X-Dev-Actor-Id": actor.json()["id"]},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _thread(client: AsyncClient, project_id: str, actor_id: str, title: str = "T") -> str:
    resp = await client.post(
        f"/api/v1/projects/{project_id}/threads",
        json={"title": title, "question": "q?"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _claim(client: AsyncClient, thread_id: str, actor_id: str, statement: str) -> str:
    resp = await client.post(
        f"/api/v1/threads/{thread_id}/claims",
        json={"kind": "hypothesis", "statement": statement},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _evidence(client: AsyncClient, claim_id: str, actor_id: str, title: str) -> str:
    resp = await client.post(
        f"/api/v1/claims/{claim_id}/evidence",
        json={"title": title, "source_type": "paper", "relation_kind": "support"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _checkpoint(client: AsyncClient, project_id: str, actor_id: str) -> str:
    resp = await client.post(
        f"/api/v1/projects/{project_id}/checkpoints",
        json={"summary": "a checkpoint"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _validate(
    client: AsyncClient, project_id: str, actor_id: str, claim_id: str, outcome: str
) -> None:
    resp = await client.post(
        f"/api/v1/projects/{project_id}/validations",
        json={"target_type": "claim", "target_id": claim_id, "outcome": outcome},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert resp.status_code == 201, resp.text


async def _branch(
    client: AsyncClient, project_id: str, actor_id: str, from_checkpoint: str
) -> str:
    resp = await client.post(
        f"/api/v1/projects/{project_id}/branches",
        json={"from_checkpoint_id": from_checkpoint, "name": "alt"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_project_overview_counts(client: AsyncClient) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client)
    thread_a = await _thread(client, project_id, actor_id, "A")
    await _thread(client, project_id, actor_id, "B")
    claim_id = await _claim(client, thread_a, actor_id, "X causes Y")
    await _evidence(client, claim_id, actor_id, "Smith 2024")
    await client.post(
        f"/api/v1/projects/{project_id}/checkpoints",
        json={"summary": "first move"},
        headers={"X-Dev-Actor-Id": actor_id},
    )

    overview = await client.get(f"/api/v1/projects/{project_id}/overview")
    assert overview.status_code == 200, overview.text
    body = overview.json()
    assert body["id"] == project_id
    assert body["title"] == "Test Project"
    assert body["counts"] == {
        "threads": 2,
        "claims": 1,
        "evidence": 1,
        "checkpoints": 1,
        "validations": 0,
        "branches": 0,
    }


async def test_overview_missing_project_404(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/projects/00000000-0000-0000-0000-000000000000/overview")
    assert resp.status_code == 404


async def test_thread_list_includes_claim_count(client: AsyncClient) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client)
    busy = await _thread(client, project_id, actor_id, "busy")
    await _thread(client, project_id, actor_id, "empty")
    await _claim(client, busy, actor_id, "c1")
    await _claim(client, busy, actor_id, "c2")

    listed = await client.get(f"/api/v1/projects/{project_id}/threads")
    assert listed.status_code == 200, listed.text
    by_title = {t["title"]: t["claim_count"] for t in listed.json()}
    assert by_title == {"busy": 2, "empty": 0}


async def test_checkpoint_read_is_enriched(client: AsyncClient) -> None:
    actor_id = await _actor(client, name="Grace")
    project_id = await _project(client)
    thread_id = await _thread(client, project_id, actor_id)
    claim_id = await _claim(client, thread_id, actor_id, "X is caused by Y")
    evidence_id = await _evidence(client, claim_id, actor_id, "Smith 2024")

    created = await client.post(
        f"/api/v1/projects/{project_id}/checkpoints",
        json={
            "thread_id": thread_id,
            "summary": "Recorded claim with evidence",
            "refs": [
                {"target_type": "claim", "target_id": claim_id, "role": "asserted"},
                {"target_type": "evidence", "target_id": evidence_id, "role": "cited"},
            ],
        },
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert created.status_code == 201, created.text
    checkpoint_id = created.json()["id"]

    detail = await client.get(f"/api/v1/checkpoints/{checkpoint_id}")
    assert detail.status_code == 200, detail.text
    body = detail.json()

    # creating actor
    assert body["author"] is not None
    assert body["author"]["display_name"] == "Grace"
    assert body["author"]["type"] == "human"
    # contribution kind recorded for this checkpoint
    assert body["contribution_kind"] == "create_checkpoint"
    # referenced primitive labels resolved server-side
    labels = {ref["target_type"]: ref["label"] for ref in body["refs"]}
    assert labels == {"claim": "X is caused by Y", "evidence": "Smith 2024"}

    # the same enrichment is present in the project listing
    listed = await client.get(f"/api/v1/projects/{project_id}/checkpoints")
    assert listed.status_code == 200
    assert listed.json()[0]["author"]["display_name"] == "Grace"


async def test_claim_read_validation_history_and_signal(client: AsyncClient) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client)
    thread_id = await _thread(client, project_id, actor_id)
    passing = await _claim(client, thread_id, actor_id, "well-supported claim")
    contested = await _claim(client, thread_id, actor_id, "shaky claim")

    await _validate(client, project_id, actor_id, passing, "passed")
    await _validate(client, project_id, actor_id, contested, "contradicts")

    listed = (await client.get(f"/api/v1/threads/{thread_id}/claims")).json()
    claims = {c["statement"]: c for c in listed}
    assert claims["well-supported claim"]["signal"] == "validated"
    assert len(claims["well-supported claim"]["validations"]) == 1
    assert claims["well-supported claim"]["validations"][0]["outcome"] == "passed"
    assert claims["shaky claim"]["signal"] == "contested"

    # A retract clears the contradiction (Decision #5 derivation, no status mutation).
    await _validate(client, project_id, actor_id, contested, "retract")
    detail = await client.get(f"/api/v1/claims/{contested}")
    assert detail.status_code == 200
    assert detail.json()["signal"] != "contested"
    assert len(detail.json()["validations"]) == 2  # history preserved, oldest first
    assert detail.json()["validations"][0]["outcome"] == "contradicts"

    # A contradiction recorded *after* the retract re-contests the claim — the signal is
    # order-aware (the latest decisive event wins), not "any retract clears everything".
    await _validate(client, project_id, actor_id, contested, "contradicts")
    detail = await client.get(f"/api/v1/claims/{contested}")
    assert detail.json()["signal"] == "contested"
    assert len(detail.json()["validations"]) == 3


async def test_overview_branch_and_validation_summaries(client: AsyncClient) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client)
    thread_id = await _thread(client, project_id, actor_id)
    claim_id = await _claim(client, thread_id, actor_id, "contested claim")
    fork = await _checkpoint(client, project_id, actor_id)

    await _validate(client, project_id, actor_id, claim_id, "contradicts")  # mints a checkpoint
    branch_id = await _branch(client, project_id, actor_id, fork)  # mints a checkpoint, open
    await client.post(
        f"/api/v1/branches/{branch_id}/close",
        json={"outcome": "dead_end", "reason": "ruled out"},
        headers={"X-Dev-Actor-Id": actor_id},
    )

    overview = (await client.get(f"/api/v1/projects/{project_id}/overview")).json()
    assert overview["counts"]["validations"] == 1
    assert overview["counts"]["branches"] == 1
    assert overview["branch_counts"] == {"open": 0, "dead_end": 1, "closed": 0}
    # the contested claim surfaces in the contradictions summary
    assert [c["claim_id"] for c in overview["contradictions"]] == [claim_id]
    assert overview["contradictions"][0]["statement"] == "contested claim"


async def test_branch_list_includes_checkpoint_count(client: AsyncClient) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client)
    fork = await _checkpoint(client, project_id, actor_id)
    # the fork checkpoint is recorded on the branch
    branch_id = await _branch(client, project_id, actor_id, fork)
    # add a second checkpoint on the branch
    resp = await client.post(
        f"/api/v1/projects/{project_id}/checkpoints",
        json={"summary": "on branch", "branch_id": branch_id},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert resp.status_code == 201, resp.text

    listed = await client.get(f"/api/v1/projects/{project_id}/branches")
    assert listed.status_code == 200
    rows = {b["id"]: b for b in listed.json()}
    assert rows[branch_id]["checkpoint_count"] == 2
    assert rows[branch_id]["status"] == "open"
