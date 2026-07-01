"""Phases 4 & 5 — the real instruments landing in the ledger through the Phase-3 write path.

DB-backed (skip without ``TEST_DATABASE_URL``). Where ``test_instruments.py`` and
``test_oeis_search.py`` prove the *math* and *retrieval*, and ``test_write_path.py`` proves the
write-path *mechanics* with stubs, this file joins them: it drives ``run_instrument`` with the
**real** instruments and asserts the durable, reproducible result — the engine version pinned in the
blame tuple, the flagship ``angle = 90°`` context recorded as assumptions (Phase 4), and (Phase 5)
an ``oeis.search`` retrieval landing as an externally-sourced, pinned ``Evidence``.

See ``docs/executing/toolbench-provenance-and-first-instruments.md`` Phases 4–5.
"""

import json
from datetime import UTC, datetime
from uuid import UUID

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.actor import Actor
from app.models.artifact import Artifact
from app.models.enums import ResultStatus
from app.models.evidence import Evidence
from app.models.links import ClaimEvidenceLink
from app.services.tool_runs import run_instrument
from app.toolbench.instruments import CALC_EVAL, COORDINATE_MEASURE
from app.toolbench.instruments._sympy_support import ENGINE_VERSION
from app.toolbench.instruments.oeis_search import OeisSearch
from app.toolbench.retrieval import Retrieval

# --- HTTP bootstrap helpers (mirror test_write_path.py) -------------------------------------------


async def _actor(client: AsyncClient) -> str:
    resp = await client.post("/api/v1/actors", json={"type": "human", "display_name": "Ada"})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _project(client: AsyncClient, slug: str) -> str:
    author = await client.post("/api/v1/actors", json={"type": "human", "display_name": "Author"})
    assert author.status_code == 201, author.text
    resp = await client.post(
        "/api/v1/projects",
        json={"title": "Toolbench", "slug": slug, "question": "What is X?"},
        headers={"X-Dev-Actor-Id": author.json()["id"]},
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


async def _claim(client: AsyncClient, thread_id: str, actor_id: str, statement: str) -> str:
    resp = await client.post(
        f"/api/v1/threads/{thread_id}/claims",
        json={"kind": "hypothesis", "statement": statement},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# --- tests ----------------------------------------------------------------------------------------


async def test_calc_eval_lands_a_result_with_the_engine_pinned(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client, "instr-calc-result")
    pid = UUID(project_id)

    async with session_factory() as session:
        actor = await session.get(Actor, UUID(actor_id))
        run = await run_instrument(
            session, pid, CALC_EVAL, actor, inputs={"expression": "3**2 + 4**2 == 5**2"}
        )

    assert run.status is ResultStatus.RESULT
    # The blame tuple records the exact engine + version that produced it (reproducibility).
    entry = run.checkpoint.tool_invocations[0]
    assert entry["instrument"] == "calc.eval"
    assert entry["engine"] == "sympy"
    assert entry["engine_version"] == ENGINE_VERSION
    assert entry["status"] == "result"
    assert entry["inputs"] == {"expression": "3**2 + 4**2 == 5**2"}
    assert entry["output"]["holds"] is True


async def test_calc_eval_false_relation_weakens_the_claim_as_a_counterexample(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client, "instr-calc-refute")
    thread_id = await _thread(client, project_id, actor_id)
    claim_id = await _claim(client, thread_id, actor_id, "5 = 7 (a deliberately false claim).")
    pid = UUID(project_id)

    async with session_factory() as session:
        actor = await session.get(Actor, UUID(actor_id))
        run = await run_instrument(
            session, pid, CALC_EVAL, actor, inputs={"expression": "5 == 7"},
            claim_id=UUID(claim_id),
        )

    assert run.status is ResultStatus.REFUTED
    assert run.evidence_id is not None

    async with session_factory() as session:
        artifact = await session.get(Artifact, run.artifact_id)
        assert artifact.kind == "counterexample"
        # A refuting run weakens the claim (outcome-derived default).
        link = (
            await session.execute(
                select(ClaimEvidenceLink).where(ClaimEvidenceLink.evidence_id == run.evidence_id)
            )
        ).scalar_one()
        assert link.relation_kind == "weaken"


async def test_geometry_corner_records_its_assumption_on_the_artifact(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    """The flagship: 'measuring across a corner' lands dist=5, angle=90°, and the assumption."""
    actor_id = await _actor(client)
    project_id = await _project(client, "instr-geo-corner")
    thread_id = await _thread(client, project_id, actor_id)
    claim_id = await _claim(client, thread_id, actor_id, "The corner spans 5 across a right angle.")
    pid = UUID(project_id)

    corner = {
        "points": {"A": [0, 0], "B": [3, 0], "C": [3, 4]},
        "distances": [["A", "C"]],
        "angles": [["A", "B", "C"]],
    }
    assumptions = {"angle_ABC_degrees": 90, "lengths_positive": True}

    async with session_factory() as session:
        actor = await session.get(Actor, UUID(actor_id))
        run = await run_instrument(
            session, pid, COORDINATE_MEASURE, actor,
            inputs=corner, assumptions=assumptions, claim_id=UUID(claim_id),
        )

    assert run.status is ResultStatus.RESULT

    async with session_factory() as session:
        artifact = await session.get(Artifact, run.artifact_id)
        assert artifact.kind == "measurement"
        # The corner's assumption is recorded verbatim on the artifact (Phase 1 spine), not lost.
        assert artifact.assumptions == assumptions

    entry = run.checkpoint.tool_invocations[0]
    assert entry["instrument"] == "geometry.coordinate_measure"
    assert entry["engine_version"] == ENGINE_VERSION
    assert entry["assumptions"] == assumptions
    assert entry["output"]["distances"] == {"A-C": "5"}
    assert entry["output"]["angles"] == {"A-B-C": {"radians": "pi/2", "degrees": "90"}}


# --- Phase 5: oeis.search (async retrieval instrument) --------------------------------------------

_FIB_OEIS_RAW = json.dumps(
    {
        "query": "1,1,2,3,5,8",
        "count": 1,
        "results": [
            {"number": 45, "name": "Fibonacci numbers.", "formula": ["F(n)=F(n-1)+F(n-2)."]}
        ],
    }
)


class _FibFetcher:
    """A fake ``Fetcher`` returning a canned OEIS Fibonacci hit — no network in this test."""

    async def get_json(self, url: str) -> Retrieval:
        return Retrieval(
            url=url,
            retrieved_at=datetime(2026, 7, 1, 12, 0, tzinfo=UTC),
            raw_response=_FIB_OEIS_RAW,
            parsed=json.loads(_FIB_OEIS_RAW),
        )


async def test_oeis_search_lands_a_pinned_external_evidence(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    """An async retrieval composes through the same chokepoint as the sync compute instruments."""
    actor_id = await _actor(client)
    project_id = await _project(client, "instr-oeis")
    thread_id = await _thread(client, project_id, actor_id)
    claim_id = await _claim(client, thread_id, actor_id, "This sequence is the Fibonacci numbers.")
    pid = UUID(project_id)

    async with session_factory() as session:
        actor = await session.get(Actor, UUID(actor_id))
        run = await run_instrument(
            session, pid, OeisSearch(_FibFetcher()), actor,
            inputs={"terms": [1, 1, 2, 3, 5, 8]}, claim_id=UUID(claim_id),
        )

    assert run.status is ResultStatus.RESULT
    assert run.evidence_id is not None

    async with session_factory() as session:
        artifact = await session.get(Artifact, run.artifact_id)
        assert artifact.kind == "pinned_source"
        evidence = await session.get(Evidence, run.evidence_id)
        # The retrieval marks its evidence as externally sourced, not the generic "tool".
        assert evidence.source_type == "oeis"

    # The blame tuple carries the pin — the A-number, retrieved_at, and the raw-response hash.
    entry = run.checkpoint.tool_invocations[0]
    assert entry["instrument"] == "oeis.search"
    pin = entry["output"]["pin"]
    assert pin["identifier"] == "A000045"
    assert pin["url"] == "https://oeis.org/A000045"
    assert pin["retrieved_at"] and pin["raw_response_hash"]
