"""Phase 6 — the human-invokable toolbench API surface (``GET /instruments`` + run).

Two DB-free gate tests (they never touch the database, so they run in the default suite): the
catalog is public, and an unauthenticated run is ``401`` (the 0.6.5 auth-gate regression pattern).
The rest is DB-backed and skips without ``TEST_DATABASE_URL``: the signed-in-member round-trip (run
``calc.eval`` over the API → ``201`` and the checkpoint appears in the ledger), plus the
``404`` / ``403`` / ``422`` edges.

See ``docs/executing/toolbench-provenance-and-first-instruments.md`` Phase 6.
"""

from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import settings
from app.models.checkpoint import Checkpoint

_BOGUS_PROJECT = "00000000-0000-0000-0000-000000000000"


# --- DB-free gates (run in the default suite) -----------------------------------------------------


def test_instruments_catalog_is_public(dbfree_client: TestClient) -> None:
    # Static reference data, no auth and no DB — like GET /agent-models/catalog.
    resp = dbfree_client.get("/api/v1/instruments")
    assert resp.status_code == 200, resp.text
    names = {d["name"] for d in resp.json()}
    assert {"calc.eval", "expr.compare", "geometry.coordinate_measure", "oeis.search"} <= names
    # every descriptor carries the universal three-outcome contract
    contract = {o["status"] for o in resp.json()[0]["result_contract"]}
    assert contract == {"result", "refuted", "undecided"}


def test_unauthenticated_run_is_rejected(
    dbfree_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # With the dev-header path off, a run with no bearer token is 401 from the ActingActor gate —
    # before any DB access (the project id never resolves; a valid-looking body proves the 401 is
    # the auth gate, not body validation or a 404).
    monkeypatch.setattr(settings, "auth_dev_header_enabled", False)
    resp = dbfree_client.post(
        f"/api/v1/projects/{_BOGUS_PROJECT}/instruments/calc.eval/run",
        json={"inputs": {"expression": "2 + 2"}},
    )
    assert resp.status_code == 401, resp.text


# --- DB-backed round-trip + edges (skip without TEST_DATABASE_URL) --------------------------------


async def _project_owned_by(client: AsyncClient, actor_id: str, slug: str) -> str:
    resp = await client.post(
        "/api/v1/projects",
        json={"title": "Toolbench", "slug": slug, "question": "What is X?"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_run_calc_eval_over_the_api(
    client: AsyncClient, session_factory: async_sessionmaker, internal_funder
) -> None:
    actor_id, _ = await internal_funder(client, roles=(), display_name="Runner")
    project_id = await _project_owned_by(client, actor_id, "api-calc")

    resp = await client.post(
        f"/api/v1/projects/{project_id}/instruments/calc.eval/run",
        json={"inputs": {"expression": "3**2 + 4**2 == 5**2"}},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "result"
    assert body["artifact_id"]
    # the blame tuple rides on the returned checkpoint, so the frontend can render provenance
    tuples = body["checkpoint"]["tool_invocations"]
    assert tuples[0]["instrument"] == "calc.eval"
    assert tuples[0]["output"]["holds"] is True

    # the checkpoint really landed in the project's ledger
    async with session_factory() as session:
        checkpoints = (
            await session.execute(
                select(Checkpoint).where(Checkpoint.project_id == UUID(project_id))
            )
        ).scalars().all()
        assert len(checkpoints) == 1


async def test_unknown_instrument_is_404(
    client: AsyncClient, internal_funder
) -> None:
    actor_id, _ = await internal_funder(client, roles=(), display_name="Runner")
    project_id = await _project_owned_by(client, actor_id, "api-404")
    resp = await client.post(
        f"/api/v1/projects/{project_id}/instruments/nope.missing/run",
        json={"inputs": {}},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert resp.status_code == 404, resp.text


async def test_non_member_is_403(client: AsyncClient, internal_funder) -> None:
    owner_id, _ = await internal_funder(client, roles=(), display_name="Owner")
    project_id = await _project_owned_by(client, owner_id, "api-403")
    # A different account-backed actor, not a member of the project.
    outsider_id, _ = await internal_funder(client, roles=(), display_name="Outsider")

    resp = await client.post(
        f"/api/v1/projects/{project_id}/instruments/calc.eval/run",
        json={"inputs": {"expression": "2 + 2"}},
        headers={"X-Dev-Actor-Id": outsider_id},
    )
    assert resp.status_code == 403, resp.text


async def test_bad_inputs_is_422(client: AsyncClient, internal_funder) -> None:
    actor_id, _ = await internal_funder(client, roles=(), display_name="Runner")
    project_id = await _project_owned_by(client, actor_id, "api-422")
    # 'expression' is required by calc.eval's InputModel; the mismatch is a 422 from the service.
    resp = await client.post(
        f"/api/v1/projects/{project_id}/instruments/calc.eval/run",
        json={"inputs": {"not_expression": 1}},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert resp.status_code == 422, resp.text
