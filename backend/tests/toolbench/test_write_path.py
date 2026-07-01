"""Phase 3 — the tool-run write path, composed through the checkpoint chokepoint.

DB-backed (skip without ``TEST_DATABASE_URL``). Drives ``run_instrument`` with stub instruments and
asserts against the ledger directly: a no-claim run mints artifact + checkpoint + one ``tool_run``
contribution atomically and the blame tuple round-trips; a claim-targeted run also mints evidence +
both links with the outcome-derived relation; ``undecided`` is recorded (not an error); and a forced
engine error leaves zero rows.

See ``docs/executing/toolbench-provenance-and-first-instruments.md`` Phase 3.
"""

from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.actor import Actor
from app.models.artifact import Artifact
from app.models.checkpoint import Checkpoint
from app.models.contribution import Contribution
from app.models.enums import ActorType, ResultStatus
from app.models.evidence import Evidence
from app.models.links import CheckpointRef, ClaimEvidenceLink, EvidenceArtifactLink
from app.services.tool_runs import _canonical_output_hash, run_instrument
from app.toolbench.adapter import InstrumentResult

# --- stub instruments (test-only) -----------------------------------------------------------------


class _StubInputs(BaseModel):
    value: int


class _StubOutput(BaseModel):
    value: int


class Stub:
    """A configurable conforming instrument: pick its outcome / artifact kind, or make it raise."""

    version = "0.1.0"
    engine = "sympy"
    engine_version = "1.13.2"
    description = "A stub instrument for the write-path tests."
    InputModel = _StubInputs
    OutputModel = _StubOutput

    def __init__(
        self,
        name: str,
        *,
        status: ResultStatus = ResultStatus.RESULT,
        artifact_kind: str = "derivation",
        raises: bool = False,
    ) -> None:
        self.name = name
        self.namespace = name.split(".", 1)[0]
        self._status = status
        self._kind = artifact_kind
        self._raises = raises

    def run(self, inputs: _StubInputs, assumptions: dict[str, Any]) -> InstrumentResult:
        if self._raises:
            raise RuntimeError("engine exploded")
        return InstrumentResult(
            output={"value": inputs.value}, status=self._status, artifact_kind=self._kind
        )


# --- HTTP bootstrap helpers -----------------------------------------------------------------------


async def _actor(client: AsyncClient) -> str:
    resp = await client.post("/api/v1/actors", json={"type": "human", "display_name": "Ada"})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _project(client: AsyncClient, slug: str) -> str:
    author = await client.post(
        "/api/v1/actors", json={"type": "human", "display_name": "Author"}
    )
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


async def _claim(client: AsyncClient, thread_id: str, actor_id: str) -> str:
    resp = await client.post(
        f"/api/v1/threads/{thread_id}/claims",
        json={"kind": "hypothesis", "statement": "3^2 + 4^2 = 5^2."},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _rows(session_factory: async_sessionmaker, model: type, project_id: UUID) -> list:
    async with session_factory() as session:
        result = await session.execute(select(model).where(model.project_id == project_id))
        return list(result.scalars())


# --- tests ----------------------------------------------------------------------------------------


async def test_run_with_no_claim_mints_artifact_checkpoint_contribution(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client, "toolrun-no-claim")
    pid = UUID(project_id)

    async with session_factory() as session:
        actor = await session.get(Actor, UUID(actor_id))
        run = await run_instrument(
            session,
            pid,
            Stub("calc.eval"),
            actor,
            inputs={"value": 25},
            assumptions={"positive": True},
        )

    assert run.status is ResultStatus.RESULT
    assert run.evidence_id is None
    assert run.content_hash

    # Exactly one artifact, one checkpoint, one tool_run contribution — and no evidence.
    artifacts = await _rows(session_factory, Artifact, pid)
    checkpoints = await _rows(session_factory, Checkpoint, pid)
    evidence = await _rows(session_factory, Evidence, pid)
    assert len(artifacts) == 1
    assert len(checkpoints) == 1
    assert evidence == []
    artifact = artifacts[0]
    assert artifact.kind == "derivation"
    assert artifact.assumptions == {"positive": True}
    assert artifact.content_hash == run.content_hash

    async with session_factory() as session:
        contribs = (
            await session.execute(
                select(Contribution).where(
                    Contribution.project_id == pid, Contribution.action == "tool_run"
                )
            )
        ).scalars().all()
        assert len(contribs) == 1
        assert contribs[0].checkpoint_id == checkpoints[0].id

    # The blame tuple round-trips off the append-only checkpoint, stamped with the artifact id.
    tuples = run.checkpoint.tool_invocations
    assert len(tuples) == 1
    entry = tuples[0]
    assert entry["instrument"] == "calc.eval"
    assert entry["engine_version"] == "1.13.2"
    assert entry["status"] == "result"
    assert entry["assumptions"] == {"positive": True}
    assert entry["produced_artifact_id"] == str(artifact.id)
    assert entry["inputs"] == {"value": 25}


async def test_run_targeting_claim_mints_evidence_and_links(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client, "toolrun-claim")
    thread_id = await _thread(client, project_id, actor_id)
    claim_id = await _claim(client, thread_id, actor_id)
    pid = UUID(project_id)

    async with session_factory() as session:
        actor = await session.get(Actor, UUID(actor_id))
        run = await run_instrument(
            session,
            pid,
            Stub("calc.eval", status=ResultStatus.REFUTED, artifact_kind="counterexample"),
            actor,
            inputs={"value": 7},
            claim_id=UUID(claim_id),
        )

    assert run.status is ResultStatus.REFUTED
    assert run.evidence_id is not None

    evidence = await _rows(session_factory, Evidence, pid)
    assert len(evidence) == 1
    assert evidence[0].source_type == "tool"

    async with session_factory() as session:
        # Claim→evidence link: a refuting run weakens the claim (outcome-derived default).
        ce_links = (
            await session.execute(
                select(ClaimEvidenceLink).where(ClaimEvidenceLink.claim_id == UUID(claim_id))
            )
        ).scalars().all()
        assert len(ce_links) == 1
        assert ce_links[0].relation_kind == "weaken"
        assert ce_links[0].evidence_id == run.evidence_id

        # Evidence→artifact link: derived_from.
        ea_links = (
            await session.execute(
                select(EvidenceArtifactLink).where(
                    EvidenceArtifactLink.evidence_id == run.evidence_id
                )
            )
        ).scalars().all()
        assert len(ea_links) == 1
        assert ea_links[0].artifact_id == run.artifact_id
        assert ea_links[0].role == "derived_from"

        # The checkpoint references the artifact (produced), evidence (recorded), claim (evidenced).
        refs = (
            await session.execute(
                select(CheckpointRef).where(CheckpointRef.checkpoint_id == run.checkpoint.id)
            )
        ).scalars().all()
        by_type = {r.target_type: r.role for r in refs}
        assert by_type == {"artifact": "produced", "evidence": "recorded", "claim": "evidenced"}


async def test_relation_kind_override_is_honoured(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client, "toolrun-relation-override")
    thread_id = await _thread(client, project_id, actor_id)
    claim_id = await _claim(client, thread_id, actor_id)
    pid = UUID(project_id)

    async with session_factory() as session:
        actor = await session.get(Actor, UUID(actor_id))
        run = await run_instrument(
            session,
            pid,
            Stub("calc.eval"),  # a RESULT would default to "support"
            actor,
            inputs={"value": 25},
            claim_id=UUID(claim_id),
            relation_kind="context",  # explicit override wins
        )

    async with session_factory() as session:
        link = (
            await session.execute(
                select(ClaimEvidenceLink).where(
                    ClaimEvidenceLink.evidence_id == run.evidence_id
                )
            )
        ).scalar_one()
        assert link.relation_kind == "context"


async def test_undecided_is_a_recorded_outcome(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client, "toolrun-undecided")
    thread_id = await _thread(client, project_id, actor_id)
    claim_id = await _claim(client, thread_id, actor_id)
    pid = UUID(project_id)

    async with session_factory() as session:
        actor = await session.get(Actor, UUID(actor_id))
        run = await run_instrument(
            session,
            pid,
            Stub("expr.compare", status=ResultStatus.UNDECIDED),
            actor,
            inputs={"value": 1},
            claim_id=UUID(claim_id),
        )

    # An undecided run is a *successful* run: it is recorded, not raised.
    assert run.status is ResultStatus.UNDECIDED
    assert len(await _rows(session_factory, Checkpoint, pid)) == 1
    assert run.checkpoint.tool_invocations[0]["status"] == "undecided"

    async with session_factory() as session:
        link = (
            await session.execute(
                select(ClaimEvidenceLink).where(
                    ClaimEvidenceLink.evidence_id == run.evidence_id
                )
            )
        ).scalar_one()
        assert link.relation_kind == "context"  # undecided → context (never support/weaken)


async def test_engine_error_leaves_zero_rows(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client, "toolrun-boom")
    pid = UUID(project_id)

    async with session_factory() as session:
        actor = await session.get(Actor, UUID(actor_id))
        with pytest.raises(HTTPException) as exc_info:
            await run_instrument(
                session, pid, Stub("boom.fail", raises=True), actor, inputs={"value": 1}
            )
        assert exc_info.value.status_code == 422

    # A tool exception mints nothing: no artifact, no checkpoint, no tool_run contribution.
    assert await _rows(session_factory, Artifact, pid) == []
    assert await _rows(session_factory, Checkpoint, pid) == []
    async with session_factory() as session:
        contribs = (
            await session.execute(
                select(Contribution).where(
                    Contribution.project_id == pid, Contribution.action == "tool_run"
                )
            )
        ).scalars().all()
        assert contribs == []


# --- DB-free: the failure split touches the session *not at all* before raising -------------------
#
# These run in the default suite (no DB). They pin the load-bearing invariant — a tool exception /
# bad inputs mint nothing — hermetically: the session raises on *any* access, so if a future edit
# adds a db call before the run, the test fails loudly instead of silently reaching a real database.


class _NoDbSession:
    """A session stand-in whose every attribute access fails — the run must not touch it."""

    def __getattr__(self, name: str) -> object:
        raise AssertionError(f"tool run touched the DB (session.{name}) on a failure path")


def _detached_actor() -> Actor:
    # A plain unsaved ORM object; never persisted, only needed for the (never-reached) attribution.
    return Actor(type=ActorType.HUMAN, display_name="Ada")


async def test_engine_error_raises_422_without_touching_the_session() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await run_instrument(
            _NoDbSession(),  # type: ignore[arg-type]
            uuid4(),
            Stub("boom.fail", raises=True),
            _detached_actor(),
            inputs={"value": 1},
        )
    assert exc_info.value.status_code == 422


async def test_invalid_inputs_raise_422_without_touching_the_session() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await run_instrument(
            _NoDbSession(),  # type: ignore[arg-type]
            uuid4(),
            Stub("calc.eval"),
            _detached_actor(),
            inputs={"value": "not-an-int"},  # fails InputModel validation
        )
    assert exc_info.value.status_code == 422


def test_canonical_output_hash_is_stable_and_key_order_independent() -> None:
    h1 = _canonical_output_hash({"a": 1, "b": 2})
    h2 = _canonical_output_hash({"b": 2, "a": 1})
    assert h1 == h2
    assert len(h1) == 64  # sha256 hexdigest
    assert _canonical_output_hash({"a": 1}) != h1
