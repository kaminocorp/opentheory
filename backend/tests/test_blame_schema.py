"""DB-free gates for the 0.36.0 semantic blame read.

OpenAPI surface, touch classification, instrument collection, agent-run link.
The HTTP round-trips that need a ledger live in ``test_blame.py``.
"""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from app.main import create_app
from app.schemas.blame import BlameInstrument
from app.services.blame import classify_touch, collect_blame_instruments, link_agent_run


def _openapi_paths() -> dict:
    return create_app().openapi()["paths"]


def test_blame_path_is_get_only() -> None:
    paths = _openapi_paths()
    route = "/api/v1/projects/{project_id}/claims/{claim_id}/blame"
    assert route in paths
    methods = set(paths[route])
    assert methods == {"get"}


def test_blame_read_does_not_require_acting_actor() -> None:
    paths = _openapi_paths()
    params = paths["/api/v1/projects/{project_id}/claims/{claim_id}/blame"]["get"].get(
        "parameters", []
    )
    header_names = {p["name"].lower() for p in params if p["in"] == "header"}
    assert "x-dev-actor-id" not in header_names


def test_classify_touch_none_when_unrelated() -> None:
    checkpoint_id, claim_id, other = uuid4(), uuid4(), uuid4()
    assert (
        classify_touch(
            checkpoint_id=checkpoint_id,
            claim_id=claim_id,
            refs=[(checkpoint_id, "claim", other, "asserted")],
            evidence_ids=set(),
            validation_ids=set(),
            has_instruments=True,
        )
        is None
    )


def test_classify_touch_claim_and_instrument() -> None:
    checkpoint_id, claim_id = uuid4(), uuid4()
    roles = classify_touch(
        checkpoint_id=checkpoint_id,
        claim_id=claim_id,
        refs=[(checkpoint_id, "claim", claim_id, "evidenced")],
        evidence_ids=set(),
        validation_ids=set(),
        has_instruments=True,
    )
    assert roles == ["evidenced", "instrument"]


def test_classify_touch_evidence_and_validation() -> None:
    checkpoint_id, claim_id = uuid4(), uuid4()
    evidence_id, validation_id = uuid4(), uuid4()
    roles = classify_touch(
        checkpoint_id=checkpoint_id,
        claim_id=claim_id,
        refs=[
            (checkpoint_id, "evidence", evidence_id, "recorded"),
            (checkpoint_id, "validation", validation_id, "recorded"),
        ],
        evidence_ids={evidence_id},
        validation_ids={validation_id},
        has_instruments=False,
    )
    assert roles == ["evidence", "validated"]


def test_collect_blame_instruments_skips_malformed_and_sorts() -> None:
    rows = collect_blame_instruments(
        [
            {"instrument": "z3.prove", "status": "result", "engine": "z3"},
            {"instrument": "broken", "status": "nope"},
            {"not": "an instrument"},
            {"instrument": "calc.eval", "status": "undecided", "instrument_version": "0.1.0"},
        ]
    )
    assert [row.instrument for row in rows] == ["calc.eval", "z3.prove"]
    assert rows[0].status == "undecided"
    assert rows[0].instrument_version == "0.1.0"
    assert rows[1].status == "result"
    assert rows[1].engine == "z3"
    again = collect_blame_instruments(
        [
            {"instrument": "z3.prove", "status": "result", "engine": "z3"},
            {"instrument": "broken", "status": "nope"},
            {"not": "an instrument"},
            {"instrument": "calc.eval", "status": "undecided", "instrument_version": "0.1.0"},
        ]
    )
    assert [BlameInstrument.model_validate(r).model_dump() for r in again] == [
        BlameInstrument.model_validate(r).model_dump() for r in rows
    ]


def test_link_agent_run_picks_newest_match() -> None:
    checkpoint_id = uuid4()
    older = SimpleNamespace(
        id=uuid4(),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        role="researcher",
        model="old",
        status="completed",
        steps=[{"checkpoint_id": str(checkpoint_id)}],
    )
    newer = SimpleNamespace(
        id=uuid4(),
        created_at=datetime(2026, 1, 2, tzinfo=UTC),
        role="research_lead",
        model="new",
        status="completed",
        steps=[{"checkpoint_id": str(checkpoint_id), "instrument": "calc.eval"}],
    )
    other = SimpleNamespace(
        id=uuid4(),
        created_at=datetime(2026, 1, 3, tzinfo=UTC),
        role="researcher",
        model="other",
        status="completed",
        steps=[{"checkpoint_id": str(uuid4())}],
    )
    linked = link_agent_run(checkpoint_id, [older, newer, other])  # type: ignore[arg-type]
    assert linked is not None
    assert linked.id == newer.id
    assert linked.role == "research_lead"
    assert linked.model == "new"


def test_link_agent_run_none_when_unmatched() -> None:
    run = SimpleNamespace(
        id=uuid4(),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        role="researcher",
        model="x",
        status="completed",
        steps=[{"checkpoint_id": None}],
    )
    assert link_agent_run(uuid4(), [run]) is None  # type: ignore[arg-type]
