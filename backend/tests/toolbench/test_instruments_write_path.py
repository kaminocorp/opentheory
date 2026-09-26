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

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import settings
from app.models.actor import Actor
from app.models.artifact import Artifact
from app.models.enums import ResultStatus
from app.models.evidence import Evidence
from app.models.links import ClaimEvidenceLink
from app.services.tool_runs import run_instrument
from app.toolbench.instruments import (
    CALC_EVAL,
    COORDINATE_MEASURE,
    COUNTEREXAMPLE_SEARCH,
    INTERVAL_EVAL,
    LEAN_PROVE,
    PLOT_FUNCTION,
    TABLE_CREATE,
    TABLE_DERIVE_COLUMN,
    Z3_PROVE,
    Z3_SATISFY,
)
from app.toolbench.instruments._lean_support import LeanCheck
from app.toolbench.instruments._sympy_support import ENGINE_VERSION
from app.toolbench.instruments._z3_support import ENGINE_VERSION as Z3_ENGINE_VERSION
from app.toolbench.instruments.arxiv_lookup import ArxivLookup
from app.toolbench.instruments.crossref_lookup import CrossrefLookup
from app.toolbench.instruments.oeis_search import OeisSearch
from app.toolbench.instruments.openalex_lookup import OpenAlexLookup
from app.toolbench.retrieval import Retrieval

# --- HTTP bootstrap helpers (mirror test_write_path.py) -------------------------------------------


async def _actor(client: AsyncClient) -> str:
    from tests.principals import make_dev_principal

    return await make_dev_principal(client)


async def _project(
    client: AsyncClient, slug: str = "test-project", actor_id: str | None = None
) -> str:
    from tests.principals import create_owned_project, make_dev_principal

    if actor_id is None:
        actor_id = await make_dev_principal(client, display_name="Author")
    return await create_owned_project(client, actor_id, slug)


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
    project_id = await _project(client, "instr-calc-result", actor_id=actor_id)
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
    project_id = await _project(client, "instr-calc-refute", actor_id=actor_id)
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
    project_id = await _project(client, "instr-geo-corner", actor_id=actor_id)
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


# --- Phase 0.10.2: counterexample.search --------------------------------------------------------

_GEOMETRY_STORY_SEARCH = {
    "relation": "d == a + b",
    "variables": {"a": {"min": 3, "max": 3}, "b": {"min": 4, "max": 4}, "d": {"min": 5, "max": 5}},
}


async def test_counterexample_search_refutes_a_claim_as_a_counterexample(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client, "instr-ce-refute", actor_id=actor_id)
    thread_id = await _thread(client, project_id, actor_id)
    claim_id = await _claim(
        client, thread_id, actor_id, "Return distance equals the sum of the legs."
    )
    pid = UUID(project_id)

    async with session_factory() as session:
        actor = await session.get(Actor, UUID(actor_id))
        run = await run_instrument(
            session,
            pid,
            COUNTEREXAMPLE_SEARCH,
            actor,
            inputs=_GEOMETRY_STORY_SEARCH,
            claim_id=UUID(claim_id),
        )

    assert run.status is ResultStatus.REFUTED
    assert run.evidence_id is not None

    async with session_factory() as session:
        artifact = await session.get(Artifact, run.artifact_id)
        assert artifact.kind == "counterexample"
        link = (
            await session.execute(
                select(ClaimEvidenceLink).where(ClaimEvidenceLink.evidence_id == run.evidence_id)
            )
        ).scalar_one()
        assert link.relation_kind == "weaken"

    entry = run.checkpoint.tool_invocations[0]
    assert entry["instrument"] == "counterexample.search"
    assert entry["engine_version"] == ENGINE_VERSION
    assert entry["output"]["found"] is True
    assert entry["output"]["witness_relation"] == "5 == 7"


async def test_counterexample_search_no_find_supports_weakly(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client, "instr-ce-weak", actor_id=actor_id)
    thread_id = await _thread(client, project_id, actor_id)
    claim_id = await _claim(client, thread_id, actor_id, "Addition commutes on small integers.")
    pid = UUID(project_id)

    async with session_factory() as session:
        actor = await session.get(Actor, UUID(actor_id))
        run = await run_instrument(
            session,
            pid,
            COUNTEREXAMPLE_SEARCH,
            actor,
            inputs={
                "relation": "a + b == b + a",
                "variables": {"a": {"min": 1, "max": 3}, "b": {"min": 1, "max": 3}},
            },
            claim_id=UUID(claim_id),
        )

    assert run.status is ResultStatus.RESULT
    assert run.evidence_id is not None

    async with session_factory() as session:
        artifact = await session.get(Artifact, run.artifact_id)
        assert artifact.kind == "derivation"
        link = (
            await session.execute(
                select(ClaimEvidenceLink).where(ClaimEvidenceLink.evidence_id == run.evidence_id)
            )
        ).scalar_one()
        # Weak support — the search ran and found no witness in the stated space.
        assert link.relation_kind == "support"

    entry = run.checkpoint.tool_invocations[0]
    assert entry["output"]["found"] is False
    assert entry["output"]["samples_tried"] == 9


# --- Phase 5: oeis.search (async retrieval instrument) --------------------------------------------

_FIB_OEIS_RAW = json.dumps(
    {
        "query": "1,1,2,3,5,8",
        "count": 1,
        "results": [
            {
                "number": 45,
                "name": "Fibonacci numbers.",
                "formula": ["F(n)=F(n-1)+F(n-2)."],
                # A real OEIS hit carries the sequence's own terms; the identification gate confirms
                # the queried run occurs here (it opens with a leading 0 before 1,1,2,3,5,8).
                "data": "0,1,1,2,3,5,8,13,21,34",
            }
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
    project_id = await _project(client, "instr-oeis", actor_id=actor_id)
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


# --- 0.18.0: literature pins through the same chokepoint -----------------------------------------

_CROSSREF_RAW = json.dumps(
    {
        "status": "ok",
        "message": {
            "DOI": "10.1038/nature14539",
            "title": ["Deep learning"],
            "author": [{"given": "Yann", "family": "LeCun"}],
            "issued": {"date-parts": [[2015]]},
            "container-title": ["Nature"],
        },
    }
)
_ARXIV_ATOM = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<feed xmlns="http://www.w3.org/2005/Atom">'
    "<entry><id>http://arxiv.org/abs/1706.03762v7</id>"
    "<title>Attention Is All You Need</title>"
    "<published>2017-06-12T00:00:00Z</published>"
    "<author><name>Ashish Vaswani</name></author></entry></feed>"
)
_OPENALEX_RAW = json.dumps(
    {
        "id": "https://openalex.org/W2963682871",
        "doi": "https://doi.org/10.1038/nature14539",
        "display_name": "Deep learning",
        "publication_year": 2015,
        "authorships": [{"author": {"display_name": "Yann LeCun"}}],
    }
)


class _CrossrefFetcher:
    async def get_json(self, url: str) -> Retrieval:
        return Retrieval(
            url=url,
            retrieved_at=datetime(2026, 9, 25, 12, 0, tzinfo=UTC),
            raw_response=_CROSSREF_RAW,
            parsed=json.loads(_CROSSREF_RAW),
        )


class _ArxivFetcher:
    async def get_text(self, url: str) -> Retrieval:
        return Retrieval(
            url=url,
            retrieved_at=datetime(2026, 9, 25, 12, 0, tzinfo=UTC),
            raw_response=_ARXIV_ATOM,
            parsed=None,
        )


class _OpenAlexFetcher:
    async def get_json(self, url: str) -> Retrieval:
        return Retrieval(
            url=url,
            retrieved_at=datetime(2026, 9, 25, 12, 0, tzinfo=UTC),
            raw_response=_OPENALEX_RAW,
            parsed=json.loads(_OPENALEX_RAW),
        )


async def test_crossref_lookup_lands_a_pinned_external_evidence(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client, "instr-crossref", actor_id=actor_id)
    thread_id = await _thread(client, project_id, actor_id)
    claim_id = await _claim(client, thread_id, actor_id, "Deep learning is a Nature paper.")
    pid = UUID(project_id)

    async with session_factory() as session:
        actor = await session.get(Actor, UUID(actor_id))
        run = await run_instrument(
            session,
            pid,
            CrossrefLookup(_CrossrefFetcher()),
            actor,
            inputs={"doi": "10.1038/nature14539"},
            claim_id=UUID(claim_id),
        )

    assert run.status is ResultStatus.RESULT
    assert run.evidence_id is not None
    async with session_factory() as session:
        artifact = await session.get(Artifact, run.artifact_id)
        assert artifact.kind == "pinned_source"
        evidence = await session.get(Evidence, run.evidence_id)
        assert evidence.source_type == "crossref"
    pin = run.checkpoint.tool_invocations[0]["output"]["pin"]
    assert pin["identifier"] == "10.1038/nature14539"
    assert pin["url"] == "https://doi.org/10.1038/nature14539"
    assert pin["retrieved_at"] and pin["raw_response_hash"]


async def test_arxiv_lookup_lands_a_pinned_external_evidence(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client, "instr-arxiv", actor_id=actor_id)
    thread_id = await _thread(client, project_id, actor_id)
    claim_id = await _claim(client, thread_id, actor_id, "Attention Is All You Need is on arXiv.")
    pid = UUID(project_id)

    async with session_factory() as session:
        actor = await session.get(Actor, UUID(actor_id))
        run = await run_instrument(
            session,
            pid,
            ArxivLookup(_ArxivFetcher()),
            actor,
            inputs={"arxiv_id": "1706.03762v7"},
            claim_id=UUID(claim_id),
        )

    assert run.status is ResultStatus.RESULT
    async with session_factory() as session:
        artifact = await session.get(Artifact, run.artifact_id)
        assert artifact.kind == "pinned_source"
        evidence = await session.get(Evidence, run.evidence_id)
        assert evidence.source_type == "arxiv"
    pin = run.checkpoint.tool_invocations[0]["output"]["pin"]
    assert pin["identifier"] == "1706.03762v7"
    assert pin["url"] == "https://arxiv.org/abs/1706.03762v7"


async def test_openalex_lookup_lands_a_pinned_external_evidence(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client, "instr-openalex", actor_id=actor_id)
    thread_id = await _thread(client, project_id, actor_id)
    claim_id = await _claim(client, thread_id, actor_id, "This work is in OpenAlex.")
    pid = UUID(project_id)

    async with session_factory() as session:
        actor = await session.get(Actor, UUID(actor_id))
        run = await run_instrument(
            session,
            pid,
            OpenAlexLookup(_OpenAlexFetcher()),
            actor,
            inputs={"doi": "10.1038/nature14539"},
            claim_id=UUID(claim_id),
        )

    assert run.status is ResultStatus.RESULT
    async with session_factory() as session:
        artifact = await session.get(Artifact, run.artifact_id)
        assert artifact.kind == "pinned_source"
        evidence = await session.get(Evidence, run.evidence_id)
        assert evidence.source_type == "openalex"
    pin = run.checkpoint.tool_invocations[0]["output"]["pin"]
    assert pin["identifier"] == "W2963682871"
    assert pin["url"] == "https://doi.org/10.1038/nature14539"


# --- Phase 0.13.5: z3.prove (the first machine-checked verifier through the chokepoint) -----------


async def test_z3_prove_lands_a_proof_with_the_z3_engine_pinned(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    """The deferred Phase 2 write path: a machine-checked proof composes through the same chokepoint
    the compute instruments use, landing a ``proof`` artifact and pinning the *Z3* engine (not
    SymPy) + version in the blame tuple — the reproduce-exactly contract for a verifier result.
    """
    actor_id = await _actor(client)
    project_id = await _project(client, "instr-z3-proof", actor_id=actor_id)
    pid = UUID(project_id)

    async with session_factory() as session:
        actor = await session.get(Actor, UUID(actor_id))
        run = await run_instrument(
            session, pid, Z3_PROVE, actor,
            inputs={
                "variables": {"x": "real", "y": "real"},
                "constraints": ["x > 0", "y > 0"],
                "goal": "x + y > 0",
            },
        )

    assert run.status is ResultStatus.RESULT

    async with session_factory() as session:
        artifact = await session.get(Artifact, run.artifact_id)
        # A proof is its own artifact kind — never styled as weak support.
        assert artifact.kind == "proof"

    entry = run.checkpoint.tool_invocations[0]
    assert entry["instrument"] == "z3.prove"
    assert entry["engine"] == "z3"
    assert entry["engine_version"] == Z3_ENGINE_VERSION
    assert entry["status"] == "result"
    assert entry["output"]["proven"] is True
    assert entry["output"]["certificate"] == "unsat"
    # The unsat-core names the hypotheses the proof actually used (index + original text).
    assert any("x > 0" in used for used in entry["output"]["used_hypotheses"])


async def test_z3_prove_refutation_weakens_the_claim_as_a_counterexample(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    """A counter-model refutes the goal → a ``counterexample`` artifact weakening the linked claim,
    exactly like the other falsifiers (outcome-derived ``weaken`` relation)."""
    actor_id = await _actor(client)
    project_id = await _project(client, "instr-z3-refute", actor_id=actor_id)
    thread_id = await _thread(client, project_id, actor_id)
    claim_id = await _claim(client, thread_id, actor_id, "x*x is never equal to x.")
    pid = UUID(project_id)

    async with session_factory() as session:
        actor = await session.get(Actor, UUID(actor_id))
        run = await run_instrument(
            session, pid, Z3_PROVE, actor,
            inputs={"variables": {"x": "int"}, "constraints": [], "goal": "x*x != x"},
            claim_id=UUID(claim_id),
        )

    assert run.status is ResultStatus.REFUTED
    assert run.evidence_id is not None

    async with session_factory() as session:
        artifact = await session.get(Artifact, run.artifact_id)
        assert artifact.kind == "counterexample"
        link = (
            await session.execute(
                select(ClaimEvidenceLink).where(ClaimEvidenceLink.evidence_id == run.evidence_id)
            )
        ).scalar_one()
        assert link.relation_kind == "weaken"

    entry = run.checkpoint.tool_invocations[0]
    assert entry["instrument"] == "z3.prove"
    assert entry["engine_version"] == Z3_ENGINE_VERSION
    assert entry["output"]["refuted"] is True
    # Exact integer witness — x=0 or x=1 both break x*x != x. Never a float.
    assert entry["output"]["witness"]["x"] in {"0", "1"}


# --- 0.33.0: z3.satisfy (model-finding through the chokepoint) ------------------------------------


async def test_z3_satisfy_lands_a_model_with_the_z3_engine_pinned(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    """A sat assignment composes through ``run_instrument`` as a ``model`` artifact, Z3-pinned."""
    actor_id = await _actor(client)
    project_id = await _project(client, "instr-z3-sat", actor_id=actor_id)
    pid = UUID(project_id)

    async with session_factory() as session:
        actor = await session.get(Actor, UUID(actor_id))
        run = await run_instrument(
            session,
            pid,
            Z3_SATISFY,
            actor,
            inputs={
                "variables": {"x": "real", "y": "real"},
                "constraints": ["x > 0", "y > 0", "x + y == 1"],
            },
        )

    assert run.status is ResultStatus.RESULT

    async with session_factory() as session:
        artifact = await session.get(Artifact, run.artifact_id)
        assert artifact.kind == "model"

    entry = run.checkpoint.tool_invocations[0]
    assert entry["instrument"] == "z3.satisfy"
    assert entry["engine"] == "z3"
    assert entry["engine_version"] == Z3_ENGINE_VERSION
    assert entry["status"] == "result"
    assert entry["output"]["satisfied"] is True
    assert entry["output"]["unsatisfiable"] is False
    model = entry["output"]["model"]
    assert set(model) == {"x", "y"}
    assert isinstance(model["x"], str)
    assert "." not in model["x"]


async def test_z3_satisfy_unsat_weakens_the_claim_with_no_model(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    """Unsat means no model exists → ``refuted`` / ``proof`` artifact, never a fake assignment."""
    actor_id = await _actor(client)
    project_id = await _project(client, "instr-z3-unsat", actor_id=actor_id)
    thread_id = await _thread(client, project_id, actor_id)
    claim_id = await _claim(client, thread_id, actor_id, "x is both positive and negative.")
    pid = UUID(project_id)

    async with session_factory() as session:
        actor = await session.get(Actor, UUID(actor_id))
        run = await run_instrument(
            session,
            pid,
            Z3_SATISFY,
            actor,
            inputs={"variables": {"x": "real"}, "constraints": ["x > 0", "x < 0"]},
            claim_id=UUID(claim_id),
        )

    assert run.status is ResultStatus.REFUTED
    assert run.evidence_id is not None

    async with session_factory() as session:
        artifact = await session.get(Artifact, run.artifact_id)
        assert artifact.kind == "proof"
        link = (
            await session.execute(
                select(ClaimEvidenceLink).where(ClaimEvidenceLink.evidence_id == run.evidence_id)
            )
        ).scalar_one()
        assert link.relation_kind == "weaken"

    entry = run.checkpoint.tool_invocations[0]
    assert entry["instrument"] == "z3.satisfy"
    assert entry["engine_version"] == Z3_ENGINE_VERSION
    assert entry["output"]["unsatisfiable"] is True
    assert entry["output"]["model"] is None
    assert entry["output"]["certificate"] == "unsat"


# --- 0.23.0: lean.prove through the chokepoint ----------------------------------------------------


async def test_lean_prove_sorry_lands_undecided_never_a_proof(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    """A sorry snippet is a recorded failed check — derivation, not proof — through the chokepoint.

    Classification is in-process (banned-construct scan) so this does not need ``lean`` installed.
    """
    actor_id = await _actor(client)
    project_id = await _project(client, "instr-lean-sorry", actor_id=actor_id)
    pid = UUID(project_id)

    async with session_factory() as session:
        actor = await session.get(Actor, UUID(actor_id))
        run = await run_instrument(
            session,
            pid,
            LEAN_PROVE,
            actor,
            inputs={"source": "example : 1 + 1 = 2 := sorry"},
        )

    assert run.status is ResultStatus.UNDECIDED
    async with session_factory() as session:
        artifact = await session.get(Artifact, run.artifact_id)
        assert artifact.kind == "derivation"
    entry = run.checkpoint.tool_invocations[0]
    assert entry["instrument"] == "lean.prove"
    assert entry["engine"] == "lean4"
    assert entry["output"]["proven"] is False
    assert entry["output"]["outcome"] == "failed"
    assert entry["output"]["status_reason"] == "rejected_constructs"


async def test_lean_prove_proof_lands_through_chokepoint_when_sandbox_in_thread(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A kernel proof composes through ``run_instrument`` — Grade A only on this status.

    Sandbox is in-thread so the monkeypatched checker runs in-process (CI has no ``lean``).
    """
    monkeypatch.setattr(settings, "toolbench_subprocess_sandbox_enabled", False)
    monkeypatch.setattr(
        "app.toolbench.instruments.lean_prove.check_source",
        lambda source, timeout_s, **_kwargs: LeanCheck(
            kind="proved",
            lean_version="4.14.0",
        ),
    )
    actor_id = await _actor(client)
    project_id = await _project(client, "instr-lean-proof", actor_id=actor_id)
    thread_id = await _thread(client, project_id, actor_id)
    claim_id = await _claim(client, thread_id, actor_id, "1 + 1 = 2")
    pid = UUID(project_id)

    async with session_factory() as session:
        actor = await session.get(Actor, UUID(actor_id))
        run = await run_instrument(
            session,
            pid,
            LEAN_PROVE,
            actor,
            inputs={"source": "example : 1 + 1 = 2 := rfl"},
            claim_id=UUID(claim_id),
        )

    assert run.status is ResultStatus.RESULT
    assert run.evidence_id is not None
    async with session_factory() as session:
        artifact = await session.get(Artifact, run.artifact_id)
        assert artifact.kind == "proof"
        link = (
            await session.execute(
                select(ClaimEvidenceLink).where(ClaimEvidenceLink.evidence_id == run.evidence_id)
            )
        ).scalar_one()
        assert link.relation_kind == "support"
    entry = run.checkpoint.tool_invocations[0]
    assert entry["instrument"] == "lean.prove"
    assert entry["output"]["proven"] is True
    assert entry["output"]["outcome"] == "proved"
    assert entry["output"]["certificate"] == "lean-kernel"


async def test_lean_prove_mathlib_import_without_opt_in_lands_undecided(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    """Mathlib import without the opt-in is a recorded failed check — never Grade A."""
    actor_id = await _actor(client)
    project_id = await _project(client, "instr-lean-mathlib-import", actor_id=actor_id)
    pid = UUID(project_id)

    async with session_factory() as session:
        actor = await session.get(Actor, UUID(actor_id))
        run = await run_instrument(
            session,
            pid,
            LEAN_PROVE,
            actor,
            inputs={
                "source": "import Mathlib\nexample : True := trivial",
                "mathlib": False,
            },
        )

    assert run.status is ResultStatus.UNDECIDED
    async with session_factory() as session:
        artifact = await session.get(Artifact, run.artifact_id)
        assert artifact.kind == "derivation"
    entry = run.checkpoint.tool_invocations[0]
    assert entry["output"]["proven"] is False
    assert entry["output"]["outcome"] == "failed"
    assert entry["output"]["status_reason"] == "rejected_constructs"


async def test_lean_prove_mathlib_proof_lands_through_chokepoint_when_sandbox_in_thread(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Mathlib kernel proof composes through ``run_instrument`` — Grade A only on this status."""
    monkeypatch.setattr(settings, "toolbench_subprocess_sandbox_enabled", False)
    monkeypatch.setattr(
        "app.toolbench.instruments.lean_prove.check_source",
        lambda source, timeout_s, **_kwargs: LeanCheck(
            kind="proved",
            lean_version="4.14.0",
            mathlib=True,
            lake_used=True,
            mathlib_rev="v4.14.0",
        ),
    )
    actor_id = await _actor(client)
    project_id = await _project(client, "instr-lean-mathlib-proof", actor_id=actor_id)
    thread_id = await _thread(client, project_id, actor_id)
    claim_id = await _claim(client, thread_id, actor_id, "(2 : ℝ) + 2 = 4")
    pid = UUID(project_id)

    async with session_factory() as session:
        actor = await session.get(Actor, UUID(actor_id))
        run = await run_instrument(
            session,
            pid,
            LEAN_PROVE,
            actor,
            inputs={
                "source": (
                    "import Mathlib.Data.Real.Basic\n"
                    "import Mathlib.Tactic.NormNum\n"
                    "example : (2 : ℝ) + 2 = 4 := by norm_num"
                ),
                "mathlib": True,
            },
            claim_id=UUID(claim_id),
        )

    assert run.status is ResultStatus.RESULT
    async with session_factory() as session:
        artifact = await session.get(Artifact, run.artifact_id)
        assert artifact.kind == "proof"
        link = (
            await session.execute(
                select(ClaimEvidenceLink).where(ClaimEvidenceLink.evidence_id == run.evidence_id)
            )
        ).scalar_one()
        assert link.relation_kind == "support"
    entry = run.checkpoint.tool_invocations[0]
    assert entry["instrument"] == "lean.prove"
    assert entry["output"]["proven"] is True
    assert entry["output"]["certificate"] == "lean-kernel+mathlib"
    assert entry["output"]["mathlib"] is True


# --- 0.34.0: Bench 6 tables / plots through the chokepoint ---------------------------------------


_TRIPLES = {
    "columns": ["a", "b", "d"],
    "rows": [{"a": 3, "b": 4, "d": 5}, {"a": 5, "b": 12, "d": 13}],
    "title": "integer triples",
}


async def test_table_create_lands_a_table_artifact(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client, "instr-table-create", actor_id=actor_id)
    pid = UUID(project_id)

    async with session_factory() as session:
        actor = await session.get(Actor, UUID(actor_id))
        run = await run_instrument(session, pid, TABLE_CREATE, actor, inputs=_TRIPLES)

    assert run.status is ResultStatus.RESULT
    async with session_factory() as session:
        artifact = await session.get(Artifact, run.artifact_id)
        assert artifact.kind == "table"
    entry = run.checkpoint.tool_invocations[0]
    assert entry["instrument"] == "table.create"
    assert entry["engine"] == "sympy"
    assert entry["engine_version"] == ENGINE_VERSION
    assert entry["output"]["n_rows"] == 2
    assert entry["output"]["exact"] is True


async def test_table_derive_column_refute_weakens_the_claim(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    """d == a+b is false on 3-4-5 — exact witness through the chokepoint."""
    actor_id = await _actor(client)
    project_id = await _project(client, "instr-table-derive", actor_id=actor_id)
    thread_id = await _thread(client, project_id, actor_id)
    claim_id = await _claim(client, thread_id, actor_id, "d equals a plus b")
    pid = UUID(project_id)

    async with session_factory() as session:
        actor = await session.get(Actor, UUID(actor_id))
        run = await run_instrument(
            session,
            pid,
            TABLE_DERIVE_COLUMN,
            actor,
            inputs={**_TRIPLES, "name": "sum_legs", "expression": "d == a + b"},
            claim_id=UUID(claim_id),
        )

    assert run.status is ResultStatus.REFUTED
    assert run.evidence_id is not None
    async with session_factory() as session:
        artifact = await session.get(Artifact, run.artifact_id)
        assert artifact.kind == "counterexample"
        link = (
            await session.execute(
                select(ClaimEvidenceLink).where(ClaimEvidenceLink.evidence_id == run.evidence_id)
            )
        ).scalar_one()
        assert link.relation_kind == "weaken"
    entry = run.checkpoint.tool_invocations[0]
    assert entry["instrument"] == "table.derive_column"
    assert entry["output"]["witness"]["d"] == "5"
    assert entry["output"]["witness"]["sum_legs"] == "false"


async def test_plot_function_lands_a_plot_artifact(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client, "instr-plot-fn", actor_id=actor_id)
    pid = UUID(project_id)

    async with session_factory() as session:
        actor = await session.get(Actor, UUID(actor_id))
        run = await run_instrument(
            session,
            pid,
            PLOT_FUNCTION,
            actor,
            inputs={
                "expression": "x**2",
                "variable": "x",
                "domain_min": "-3",
                "domain_max": "3",
                "n_samples": 7,
            },
        )

    assert run.status is ResultStatus.RESULT
    async with session_factory() as session:
        artifact = await session.get(Artifact, run.artifact_id)
        assert artifact.kind == "plot"
    entry = run.checkpoint.tool_invocations[0]
    assert entry["instrument"] == "plot.function"
    assert entry["output"]["approximate"] is True
    assert entry["output"]["spec"]["$schema"].startswith("https://vega.github.io")
    assert entry["output"]["n_plotted"] == 7


# --- 0.35.0: interval.eval through the chokepoint ------------------------------------------------


async def test_interval_eval_lands_an_enclosure_with_the_engine_pinned(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    from app.toolbench.instruments._interval_support import ENGINE as INTERVAL_ENGINE
    from app.toolbench.instruments._interval_support import ENGINE_VERSION as INTERVAL_VERSION

    actor_id = await _actor(client)
    project_id = await _project(client, "instr-interval-enc", actor_id=actor_id)
    pid = UUID(project_id)

    async with session_factory() as session:
        actor = await session.get(Actor, UUID(actor_id))
        run = await run_instrument(
            session, pid, INTERVAL_EVAL, actor, inputs={"expression": "sqrt(2)"}
        )

    assert run.status is ResultStatus.RESULT
    async with session_factory() as session:
        artifact = await session.get(Artifact, run.artifact_id)
        assert artifact.kind == "derivation"
    entry = run.checkpoint.tool_invocations[0]
    assert entry["instrument"] == "interval.eval"
    assert entry["engine"] == INTERVAL_ENGINE
    assert entry["engine_version"] == INTERVAL_VERSION
    assert entry["output"]["lo"] is not None
    assert entry["output"]["hi"] is not None
    assert entry["output"]["method"] in {"arb", "mpmath.iv"}
    assert not any(isinstance(v, float) for v in entry["output"].values())


async def test_interval_eval_refute_weakens_the_claim(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    """sqrt(2) == 2 is entirely off — proven miss through the chokepoint."""
    actor_id = await _actor(client)
    project_id = await _project(client, "instr-interval-refute", actor_id=actor_id)
    thread_id = await _thread(client, project_id, actor_id)
    claim_id = await _claim(client, thread_id, actor_id, "sqrt(2) equals 2")
    pid = UUID(project_id)

    async with session_factory() as session:
        actor = await session.get(Actor, UUID(actor_id))
        run = await run_instrument(
            session,
            pid,
            INTERVAL_EVAL,
            actor,
            inputs={"expression": "sqrt(2) == 2"},
            claim_id=UUID(claim_id),
        )

    assert run.status is ResultStatus.REFUTED
    assert run.evidence_id is not None
    async with session_factory() as session:
        artifact = await session.get(Artifact, run.artifact_id)
        assert artifact.kind == "counterexample"
        link = (
            await session.execute(
                select(ClaimEvidenceLink).where(ClaimEvidenceLink.evidence_id == run.evidence_id)
            )
        ).scalar_one()
        assert link.relation_kind == "weaken"
    entry = run.checkpoint.tool_invocations[0]
    assert entry["instrument"] == "interval.eval"
    assert entry["output"]["holds"] is False
