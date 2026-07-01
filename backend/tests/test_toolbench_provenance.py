"""Phase 1 — toolbench provenance spine.

Two layers:

- **DB-free** (always run): the strict-write contract on the ``ToolInvocation`` blame tuple —
  valid parse, malformed rejection, and ``extra="forbid"`` (a stamped grade must never sneak in).
- **DB-backed** (skip without ``TEST_DATABASE_URL``): a checkpoint carries a validated tuple that
  round-trips and is immutable via the append-only ``Checkpoint`` guard; an ``Evidence`` links to an
  ``Artifact`` and both carry assumptions; the link is *not* append-only (it can be deleted).

See ``docs/executing/toolbench-provenance-and-first-instruments.md`` Phase 1.
"""

from uuid import UUID

import pytest
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import selectinload

from app.models import AppendOnlyError
from app.models.actor import Actor
from app.models.artifact import Artifact
from app.models.checkpoint import Checkpoint
from app.models.enums import ResultStatus
from app.models.evidence import Evidence
from app.models.links import EvidenceArtifactLink
from app.schemas.checkpoint import CheckpointCreate
from app.schemas.tool_invocation import ToolInvocation
from app.services.checkpoints import create_checkpoint


def _valid_invocation(**overrides: object) -> dict[str, object]:
    """A well-formed blame tuple: SymPy settling ``3² + 4² == 5²`` exactly."""
    data: dict[str, object] = {
        "instrument": "calc.eval",
        "instrument_version": "0.1.0",
        "engine": "sympy",
        "engine_version": "1.13.2",
        "inputs": {"expr": "3**2 + 4**2 == 5**2"},
        "output": {"value": True},
        "status": ResultStatus.RESULT,
    }
    data.update(overrides)
    return data


# --------------------------------------------------------------------------------------------------
# DB-free: the strict-write contract (the "schema" half of lenient-read / strict-write).
# --------------------------------------------------------------------------------------------------


def test_tool_invocation_parses_valid() -> None:
    ti = ToolInvocation(**_valid_invocation())  # type: ignore[arg-type]
    assert ti.status is ResultStatus.RESULT
    dumped = ti.model_dump(mode="json")
    # JSON-column ready: enum -> its value, absent optional -> None, default assumptions -> {}.
    assert dumped["status"] == "result"
    assert dumped["engine_version"] == "1.13.2"
    assert dumped["assumptions"] == {}
    assert dumped["produced_artifact_id"] is None


def test_tool_invocation_carries_assumptions_and_artifact_id() -> None:
    ti = ToolInvocation(
        **_valid_invocation(  # type: ignore[arg-type]
            assumptions={"angle": 90},
            produced_artifact_id=UUID("00000000-0000-0000-0000-000000000001"),
        )
    )
    dumped = ti.model_dump(mode="json")
    assert dumped["assumptions"] == {"angle": 90}
    assert dumped["produced_artifact_id"] == "00000000-0000-0000-0000-000000000001"


@pytest.mark.parametrize(
    "bad",
    [
        {"instrument": ""},  # empty required string
        {"engine_version": None},  # required, not-null
        {"status": "bogus"},  # not a ResultStatus member
    ],
)
def test_tool_invocation_rejects_malformed(bad: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ToolInvocation(**_valid_invocation(**bad))  # type: ignore[arg-type]


def test_tool_invocation_rejects_missing_required_field() -> None:
    data = _valid_invocation()
    del data["output"]  # a blame tuple with no output is meaningless
    with pytest.raises(ValidationError):
        ToolInvocation(**data)  # type: ignore[arg-type]


def test_tool_invocation_forbids_extra_key() -> None:
    # extra="forbid" keeps a stamped grade / result-kind out of the tuple (it is *derived* from the
    # recorded instrument, never stored — docs/plans/maths-toolbox.md cross-cutting 2).
    with pytest.raises(ValidationError):
        ToolInvocation(**_valid_invocation(grade="A"))  # type: ignore[arg-type]


# --------------------------------------------------------------------------------------------------
# DB-backed: the spine holds through the chokepoint (skips without TEST_DATABASE_URL).
# --------------------------------------------------------------------------------------------------


async def _actor(client: AsyncClient) -> str:
    resp = await client.post("/api/v1/actors", json={"type": "human", "display_name": "Ada"})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _project(client: AsyncClient, slug: str = "toolbench-project") -> str:
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


async def test_checkpoint_carries_validated_tool_invocation(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client)

    ti = ToolInvocation(**_valid_invocation())  # type: ignore[arg-type]
    async with session_factory() as session:
        actor = await session.get(Actor, UUID(actor_id))
        assert actor is not None
        read = await create_checkpoint(
            session,
            UUID(project_id),
            CheckpointCreate(summary="ran calc.eval on the Pythagorean identity", content={}),
            actor,
            tool_invocations=[ti],
        )

    # Surfaced on the read model as raw JSON (the lenient-read half).
    assert len(read.tool_invocations) == 1
    entry = read.tool_invocations[0]
    assert entry["instrument"] == "calc.eval"
    assert entry["engine_version"] == "1.13.2"
    assert entry["status"] == "result"

    # Round-trips verbatim from the append-only column.
    async with session_factory() as session:
        cp = await session.get(Checkpoint, read.id)
        assert cp is not None
        assert cp.tool_invocations[0]["engine"] == "sympy"
        assert cp.tool_invocations[0]["inputs"] == {"expr": "3**2 + 4**2 == 5**2"}


async def test_tool_invocation_is_immutable_via_checkpoint_guard(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client, slug="toolbench-immutable")

    ti = ToolInvocation(**_valid_invocation())  # type: ignore[arg-type]
    async with session_factory() as session:
        actor = await session.get(Actor, UUID(actor_id))
        assert actor is not None
        read = await create_checkpoint(
            session,
            UUID(project_id),
            CheckpointCreate(summary="ran", content={}),
            actor,
            tool_invocations=[ti],
        )

    # The blame tuple rides on the append-only Checkpoint, so tampering with it is refused at the
    # ORM layer — no new guard needed (plan Phase 1, task 6).
    async with session_factory() as session:
        cp = await session.get(Checkpoint, read.id)
        assert cp is not None
        cp.tool_invocations = [{"instrument": "tampered"}]
        with pytest.raises(AppendOnlyError):
            await session.flush()


async def test_evidence_links_to_artifact_with_assumptions(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    project_id = await _project(client, slug="toolbench-links")
    pid = UUID(project_id)

    async with session_factory() as session:
        artifact = Artifact(
            project_id=pid,
            name="corner measurement",
            kind="measurement",
            assumptions={"angle": 90},
        )
        evidence = Evidence(
            project_id=pid,
            title="dist(A,C) = 5",
            source_type="tool",
            assumptions={"a": "positive", "b": "positive"},
        )
        session.add_all([artifact, evidence])
        await session.flush()
        session.add(
            EvidenceArtifactLink(
                evidence_id=evidence.id, artifact_id=artifact.id, role="derived_from"
            )
        )
        await session.commit()
        evidence_id, artifact_id = evidence.id, artifact.id

    # The link resolves both directions; assumptions persist as dedicated columns on both rows.
    async with session_factory() as session:
        ev = (
            await session.execute(
                select(Evidence)
                .where(Evidence.id == evidence_id)
                .options(selectinload(Evidence.artifact_links))
            )
        ).scalar_one()
        assert ev.assumptions == {"a": "positive", "b": "positive"}
        assert len(ev.artifact_links) == 1
        assert ev.artifact_links[0].artifact_id == artifact_id
        assert ev.artifact_links[0].role == "derived_from"

        art = (
            await session.execute(
                select(Artifact)
                .where(Artifact.id == artifact_id)
                .options(selectinload(Artifact.evidence_links))
            )
        ).scalar_one()
        assert art.assumptions == {"angle": 90}
        assert len(art.evidence_links) == 1
        assert art.evidence_links[0].evidence_id == evidence_id


async def test_evidence_artifact_link_is_not_append_only(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    project_id = await _project(client, slug="toolbench-link-mutable")
    pid = UUID(project_id)

    async with session_factory() as session:
        artifact = Artifact(project_id=pid, name="a", kind="measurement")
        evidence = Evidence(project_id=pid, title="e", source_type="tool")
        session.add_all([artifact, evidence])
        await session.flush()
        link = EvidenceArtifactLink(
            evidence_id=evidence.id, artifact_id=artifact.id, role="attachment"
        )
        session.add(link)
        await session.commit()

        # Unlike the checkpoint blame tuple, a link is not a ledger event — deleting it is allowed.
        await session.delete(link)
        await session.commit()
        remaining = (await session.execute(select(EvidenceArtifactLink))).scalars().all()
        assert remaining == []
