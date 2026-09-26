"""Phase 3 — the tool-run write path, composed through the checkpoint chokepoint.

DB-backed (skip without ``TEST_DATABASE_URL``). Drives ``run_instrument`` with registered
``test.stub*`` instruments (never production names — the 0.11.3 sandbox worker looks the
name up in the real registry) and asserts against the ledger directly: a no-claim run mints
artifact + checkpoint + one ``tool_run`` contribution atomically and the blame tuple
round-trips; a claim-targeted run also mints evidence + both links with the outcome-derived
relation; ``undecided`` is recorded (not an error); and a forced engine error leaves zero
rows.

See ``docs/executing/toolbench-provenance-and-first-instruments.md`` Phase 3.
"""

from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.actor import Actor
from app.models.artifact import Artifact
from app.models.branch import Branch
from app.models.checkpoint import Checkpoint
from app.models.contribution import Contribution
from app.models.enums import ActorType, BranchStatus, ResultStatus
from app.models.evidence import Evidence
from app.models.links import CheckpointRef, ClaimEvidenceLink, EvidenceArtifactLink
from app.services.tool_runs import _canonical_output_hash, run_instrument
from app.toolbench.execution.runner import execute_instrument
from tests.toolbench.stubs import (
    WRITE_PATH_STUB,
    WRITE_PATH_STUB_BOOM,
    WRITE_PATH_STUB_REFUTED,
    WRITE_PATH_STUB_UNDECIDED,
    WritePathStub,
    register_test_instruments,
)

# --- HTTP bootstrap helpers -----------------------------------------------------------------------


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
    project_id = await _project(client, "toolrun-no-claim", actor_id=actor_id)
    pid = UUID(project_id)

    async with session_factory() as session:
        actor = await session.get(Actor, UUID(actor_id))
        run = await run_instrument(
            session,
            pid,
            WRITE_PATH_STUB,
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
    assert entry["instrument"] == "test.stub"
    assert entry["engine_version"] == "1.0"
    assert entry["status"] == "result"
    assert entry["assumptions"] == {"positive": True}
    assert entry["produced_artifact_id"] == str(artifact.id)
    assert entry["inputs"] == {"value": 25}


async def test_run_targeting_claim_mints_evidence_and_links(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client, "toolrun-claim", actor_id=actor_id)
    thread_id = await _thread(client, project_id, actor_id)
    claim_id = await _claim(client, thread_id, actor_id)
    pid = UUID(project_id)

    async with session_factory() as session:
        actor = await session.get(Actor, UUID(actor_id))
        run = await run_instrument(
            session,
            pid,
            WRITE_PATH_STUB_REFUTED,
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
    project_id = await _project(client, "toolrun-relation-override", actor_id=actor_id)
    thread_id = await _thread(client, project_id, actor_id)
    claim_id = await _claim(client, thread_id, actor_id)
    pid = UUID(project_id)

    async with session_factory() as session:
        actor = await session.get(Actor, UUID(actor_id))
        run = await run_instrument(
            session,
            pid,
            WRITE_PATH_STUB,  # a RESULT would default to "support"
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
    project_id = await _project(client, "toolrun-undecided", actor_id=actor_id)
    thread_id = await _thread(client, project_id, actor_id)
    claim_id = await _claim(client, thread_id, actor_id)
    pid = UUID(project_id)

    async with session_factory() as session:
        actor = await session.get(Actor, UUID(actor_id))
        run = await run_instrument(
            session,
            pid,
            WRITE_PATH_STUB_UNDECIDED,
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
    project_id = await _project(client, "toolrun-boom", actor_id=actor_id)
    pid = UUID(project_id)

    async with session_factory() as session:
        actor = await session.get(Actor, UUID(actor_id))
        with pytest.raises(HTTPException) as exc_info:
            await run_instrument(
                session, pid, WRITE_PATH_STUB_BOOM, actor, inputs={"value": 1}
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


async def _open_branch(
    session_factory: async_sessionmaker, project_id: UUID, *, status: BranchStatus
) -> UUID:
    """Create a branch row directly (fork id is nullable) and return its id."""
    async with session_factory() as session:
        branch = Branch(project_id=project_id, name="exploration", status=status)
        session.add(branch)
        await session.commit()
        return branch.id


async def test_run_records_the_checkpoint_on_a_branch(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    # 0.9.8 (F1): a branch_id lands the produced checkpoint on that line, not silently on main.
    actor_id = await _actor(client)
    project_id = await _project(client, "toolrun-branch", actor_id=actor_id)
    pid = UUID(project_id)
    branch_id = await _open_branch(session_factory, pid, status=BranchStatus.OPEN)

    async with session_factory() as session:
        actor = await session.get(Actor, UUID(actor_id))
        run = await run_instrument(
            session, pid, WRITE_PATH_STUB, actor, inputs={"value": 4}, branch_id=branch_id
        )

    assert run.checkpoint.branch_id == branch_id
    checkpoints = await _rows(session_factory, Checkpoint, pid)
    assert len(checkpoints) == 1
    assert checkpoints[0].branch_id == branch_id


async def test_run_on_a_sealed_branch_is_rejected_and_mints_nothing(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    # A sealed (closed/dead-end/merged) line cannot receive checkpoints; the chokepoint rejects it.
    # This also pins the *post-flush* atomic rollback: the artifact is flushed before the chokepoint
    # validates the branch, so a clean 400 here proves the flushed artifact rolls back (no orphan).
    actor_id = await _actor(client)
    project_id = await _project(client, "toolrun-sealed-branch", actor_id=actor_id)
    pid = UUID(project_id)
    branch_id = await _open_branch(session_factory, pid, status=BranchStatus.CLOSED)

    async with session_factory() as session:
        actor = await session.get(Actor, UUID(actor_id))
        with pytest.raises(HTTPException) as exc_info:
            await run_instrument(
                session, pid, WRITE_PATH_STUB, actor, inputs={"value": 4}, branch_id=branch_id
            )
        assert exc_info.value.status_code == 400

    assert await _rows(session_factory, Artifact, pid) == []
    assert await _rows(session_factory, Checkpoint, pid) == []


async def test_thread_id_conflicting_with_the_claim_thread_is_422(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    # A claim carries its own thread; passing a *different* thread_id would mislead about where the
    # result landed, so it is a 422 (not silently ignored).
    actor_id = await _actor(client)
    project_id = await _project(client, "toolrun-thread-conflict", actor_id=actor_id)
    thread_a = await _thread(client, project_id, actor_id)
    other_thread = await _thread(client, project_id, actor_id)
    claim_id = await _claim(client, thread_a, actor_id)
    pid = UUID(project_id)

    async with session_factory() as session:
        actor = await session.get(Actor, UUID(actor_id))
        with pytest.raises(HTTPException) as exc_info:
            await run_instrument(
                session,
                pid,
                WRITE_PATH_STUB,
                actor,
                inputs={"value": 4},
                claim_id=UUID(claim_id),
                thread_id=UUID(other_thread),
            )
        assert exc_info.value.status_code == 422


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
            WRITE_PATH_STUB_BOOM,
            _detached_actor(),
            inputs={"value": 1},
        )
    assert exc_info.value.status_code == 422


async def test_invalid_inputs_raise_422_without_touching_the_session() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await run_instrument(
            _NoDbSession(),  # type: ignore[arg-type]
            uuid4(),
            WRITE_PATH_STUB,
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


def test_write_path_stub_refuses_a_production_name() -> None:
    with pytest.raises(ValueError, match=r"test\."):
        WritePathStub("calc.eval")


def test_write_path_stubs_are_test_names_not_calc_eval() -> None:
    for stub in (
        WRITE_PATH_STUB,
        WRITE_PATH_STUB_REFUTED,
        WRITE_PATH_STUB_UNDECIDED,
        WRITE_PATH_STUB_BOOM,
    ):
        assert stub.name.startswith("test.")
        assert stub.name != "calc.eval"
        assert stub.namespace == "test"


async def test_write_path_stub_dispatches_through_sandbox_by_registered_name() -> None:
    """The worker looks the name up in the real registry. A stub named calc.eval
    would run production calc.eval against {value: 25} — the 0.11.3 drift.
    """
    register_test_instruments()
    outcome = await execute_instrument(
        WRITE_PATH_STUB,
        WRITE_PATH_STUB.InputModel(value=25),
        {},
    )
    assert outcome.result.status is ResultStatus.RESULT
    assert outcome.result.output == {"value": 25}


async def test_write_path_stub_refuted_dispatches_configured_outcome() -> None:
    register_test_instruments()
    outcome = await execute_instrument(
        WRITE_PATH_STUB_REFUTED,
        WRITE_PATH_STUB_REFUTED.InputModel(value=7),
        {},
    )
    assert outcome.result.status is ResultStatus.REFUTED
    assert outcome.result.artifact_kind == "counterexample"


def test_canonical_output_hash_ignores_latex_companions() -> None:
    base = {
        "distances": {"A-C": "5"},
        "angles": {"A-B-C": {"radians": "pi/2", "degrees": "90"}},
    }
    with_latex = {
        **base,
        "distances_latex": {"A-C": "5"},
        "angles": {
            "A-B-C": {
                "radians": "pi/2",
                "degrees": "90",
                "radians_latex": r"\frac{\pi}{2}",
                "degrees_latex": "90",
            }
        },
        "expression_latex": r"x^{2}",
    }
    assert _canonical_output_hash(base) == _canonical_output_hash(with_latex)
