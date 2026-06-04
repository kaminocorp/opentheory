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
    resp = await client.post(
        "/api/v1/projects",
        json={"title": "Test Project", "slug": slug, "question": "What is X?"},
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
    assert body["counts"] == {"threads": 2, "claims": 1, "evidence": 1, "checkpoints": 1}


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
