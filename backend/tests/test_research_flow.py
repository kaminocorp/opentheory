"""DB-backed integration tests for the 0.3.1 write path.

Covers actor creation, the project -> thread -> claim -> evidence flow, every evidence
relation kind, and X-Dev-Actor-Id enforcement. These run only when a database is
configured (see conftest.py); otherwise they skip.
"""

from httpx import AsyncClient


async def _create_actor(client: AsyncClient) -> str:
    response = await client.post(
        "/api/v1/actors",
        json={"type": "human", "display_name": "Ada Researcher"},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _create_project(client: AsyncClient) -> str:
    response = await client.post(
        "/api/v1/projects",
        json={
            "title": "Test Project",
            "slug": "test-project",
            "question": "What is the nature of X?",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _create_thread(client: AsyncClient, project_id: str, actor_id: str) -> str:
    response = await client.post(
        f"/api/v1/projects/{project_id}/threads",
        json={"title": "Decompose X", "question": "What sub-questions does X have?"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _create_claim(client: AsyncClient, thread_id: str, actor_id: str) -> str:
    response = await client.post(
        f"/api/v1/threads/{thread_id}/claims",
        json={"kind": "hypothesis", "statement": "X is caused by Y.", "confidence": 0.6},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def test_actor_create_and_list(client: AsyncClient) -> None:
    actor_id = await _create_actor(client)

    response = await client.get("/api/v1/actors")
    assert response.status_code == 200
    ids = [a["id"] for a in response.json()]
    assert actor_id in ids


async def test_full_research_move_flow(client: AsyncClient) -> None:
    actor_id = await _create_actor(client)
    project_id = await _create_project(client)
    thread_id = await _create_thread(client, project_id, actor_id)

    # thread appears under its project and is retrievable on its own
    listed = await client.get(f"/api/v1/projects/{project_id}/threads")
    assert listed.status_code == 200
    assert [t["id"] for t in listed.json()] == [thread_id]

    detail = await client.get(f"/api/v1/threads/{thread_id}")
    assert detail.status_code == 200
    assert detail.json()["project_id"] == project_id
    assert detail.json()["stage"] == "decompose"

    claim_id = await _create_claim(client, thread_id, actor_id)

    claim_detail = await client.get(f"/api/v1/claims/{claim_id}")
    assert claim_detail.status_code == 200
    # claim inherits the thread's project; client never supplies project_id
    assert claim_detail.json()["project_id"] == project_id
    assert claim_detail.json()["thread_id"] == thread_id

    # attach evidence with a support relation
    ev_response = await client.post(
        f"/api/v1/claims/{claim_id}/evidence",
        json={
            "title": "Smith 2024",
            "source_type": "paper",
            "uri": "https://example.org/smith2024",
            "relation_kind": "support",
        },
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert ev_response.status_code == 201, ev_response.text
    body = ev_response.json()
    assert body["relation_kind"] == "support"
    assert body["project_id"] == project_id
    assert body["thread_id"] == thread_id

    ev_list = await client.get(f"/api/v1/claims/{claim_id}/evidence")
    assert ev_list.status_code == 200
    assert ev_list.json()[0]["relation_kind"] == "support"


async def test_each_relation_kind_is_recorded(client: AsyncClient) -> None:
    actor_id = await _create_actor(client)
    project_id = await _create_project(client)
    thread_id = await _create_thread(client, project_id, actor_id)
    claim_id = await _create_claim(client, thread_id, actor_id)

    for kind in ("support", "weaken", "context"):
        response = await client.post(
            f"/api/v1/claims/{claim_id}/evidence",
            json={"title": f"ev-{kind}", "source_type": "note", "relation_kind": kind},
            headers={"X-Dev-Actor-Id": actor_id},
        )
        assert response.status_code == 201, response.text
        assert response.json()["relation_kind"] == kind

    ev_list = await client.get(f"/api/v1/claims/{claim_id}/evidence")
    assert {e["relation_kind"] for e in ev_list.json()} == {"support", "weaken", "context"}


async def test_invalid_relation_kind_rejected(client: AsyncClient) -> None:
    actor_id = await _create_actor(client)
    project_id = await _create_project(client)
    thread_id = await _create_thread(client, project_id, actor_id)
    claim_id = await _create_claim(client, thread_id, actor_id)

    response = await client.post(
        f"/api/v1/claims/{claim_id}/evidence",
        json={"title": "bad", "source_type": "note", "relation_kind": "endorses"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert response.status_code == 422


async def test_write_requires_valid_dev_actor_header(client: AsyncClient) -> None:
    project_id = await _create_project(client)

    # missing header
    missing = await client.post(
        f"/api/v1/projects/{project_id}/threads",
        json={"title": "t", "question": "q"},
    )
    assert missing.status_code == 400

    # malformed header
    malformed = await client.post(
        f"/api/v1/projects/{project_id}/threads",
        json={"title": "t", "question": "q"},
        headers={"X-Dev-Actor-Id": "not-a-uuid"},
    )
    assert malformed.status_code == 400

    # well-formed but unknown actor
    unknown = await client.post(
        f"/api/v1/projects/{project_id}/threads",
        json={"title": "t", "question": "q"},
        headers={"X-Dev-Actor-Id": "00000000-0000-0000-0000-000000000000"},
    )
    assert unknown.status_code == 404


async def test_create_under_missing_parents_404(client: AsyncClient) -> None:
    actor_id = await _create_actor(client)
    missing_id = "00000000-0000-0000-0000-000000000000"

    thread_resp = await client.post(
        f"/api/v1/projects/{missing_id}/threads",
        json={"title": "t", "question": "q"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert thread_resp.status_code == 404

    claim_resp = await client.post(
        f"/api/v1/threads/{missing_id}/claims",
        json={"kind": "hypothesis", "statement": "s"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert claim_resp.status_code == 404

    ev_resp = await client.post(
        f"/api/v1/claims/{missing_id}/evidence",
        json={"title": "t", "source_type": "note", "relation_kind": "support"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert ev_resp.status_code == 404
