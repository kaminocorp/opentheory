"""DB-free gates for the 0.29.0 semantic diff read.

OpenAPI surface, pure graph helpers, claim classification, instrument collection.
The HTTP round-trips that need a ledger live in ``test_diff.py``.
"""

from datetime import UTC, datetime
from uuid import uuid4

from app.main import create_app
from app.schemas.diff import InstrumentOutcome
from app.services.diff import (
    classify_claim_delta,
    collect_instrument_outcomes,
    lowest_common_ancestor,
    sort_checkpoint_ids,
    walk_ancestors,
)


def _openapi_paths() -> dict:
    return create_app().openapi()["paths"]


def test_diff_path_is_get_only() -> None:
    paths = _openapi_paths()
    route = "/api/v1/projects/{project_id}/diff"
    assert route in paths
    methods = set(paths[route])
    assert methods == {"get"}


def test_diff_read_does_not_require_acting_actor() -> None:
    paths = _openapi_paths()
    params = paths["/api/v1/projects/{project_id}/diff"]["get"].get("parameters", [])
    header_names = {p["name"].lower() for p in params if p["in"] == "header"}
    assert "x-dev-actor-id" not in header_names
    query_names = {p["name"] for p in params if p["in"] == "query"}
    assert "from" in query_names
    assert "to" in query_names


def test_walk_ancestors_includes_self_and_parents() -> None:
    a, b, c = uuid4(), uuid4(), uuid4()
    parent_map = {c: [b], b: [a], a: []}
    assert walk_ancestors(a, parent_map) == {a}
    assert walk_ancestors(c, parent_map) == {a, b, c}


def test_walk_ancestors_unions_merge_parents() -> None:
    root, left, right, merge = uuid4(), uuid4(), uuid4(), uuid4()
    parent_map = {
        merge: [left, right, root],
        left: [root],
        right: [root],
        root: [],
    }
    assert walk_ancestors(merge, parent_map) == {root, left, right, merge}


def test_lowest_common_ancestor_on_a_diamond() -> None:
    root, left, right, merge = uuid4(), uuid4(), uuid4(), uuid4()
    parent_map = {
        merge: [left, right],
        left: [root],
        right: [root],
        root: [],
    }
    now = datetime(2026, 1, 1, tzinfo=UTC)
    created = {
        root: now,
        left: now.replace(day=2),
        right: now.replace(day=3),
        merge: now.replace(day=4),
    }
    from_anc = walk_ancestors(left, parent_map)
    to_anc = walk_ancestors(right, parent_map)
    assert lowest_common_ancestor(from_anc, to_anc, parent_map, created) == root


def test_sort_checkpoint_ids_is_stable() -> None:
    older, newer = uuid4(), uuid4()
    created = {
        older: datetime(2026, 1, 1, tzinfo=UTC),
        newer: datetime(2026, 1, 2, tzinfo=UTC),
    }
    assert sort_checkpoint_ids({newer, older}, created) == [older, newer]


def test_classify_empty_when_signals_match() -> None:
    assert (
        classify_claim_delta(
            claim_id=uuid4(),
            statement="X",
            present_from=True,
            present_to=True,
            from_signal="none",
            to_signal="none",
        )
        is None
    )


def test_classify_status_changed() -> None:
    claim_id = uuid4()
    row = classify_claim_delta(
        claim_id=claim_id,
        statement="X",
        present_from=True,
        present_to=True,
        from_signal="none",
        to_signal="validated",
    )
    assert row is not None
    assert row.change == "status_changed"
    assert row.from_signal == "none"
    assert row.to_signal == "validated"


def test_classify_added_and_removed() -> None:
    claim_id = uuid4()
    added = classify_claim_delta(
        claim_id=claim_id,
        statement="X",
        present_from=False,
        present_to=True,
        from_signal="none",
        to_signal="none",
    )
    assert added is not None and added.change == "added"
    removed = classify_claim_delta(
        claim_id=claim_id,
        statement="X",
        present_from=True,
        present_to=False,
        from_signal="none",
        to_signal="none",
    )
    assert removed is not None and removed.change == "removed"


class _Ckpt:
    def __init__(self, created_at: datetime, summary: str, invocations: list[dict]) -> None:
        self.created_at = created_at
        self.summary = summary
        self.tool_invocations = invocations


def test_collect_instrument_outcomes_skips_malformed_and_sorts() -> None:
    first = uuid4()
    second = uuid4()
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    t1 = datetime(2026, 1, 2, tzinfo=UTC)
    claim = uuid4()
    checkpoints = {
        first: _Ckpt(
            t0,
            "run a",
            [
                {"instrument": "z3.prove", "status": "result"},
                {"instrument": "broken", "status": "nope"},
                {"not": "an instrument"},
            ],
        ),
        second: _Ckpt(
            t1,
            "run b",
            [{"instrument": "calc.eval", "status": "undecided"}],
        ),
    }
    rows = collect_instrument_outcomes(
        interval_ids=[first, second],
        checkpoints=checkpoints,  # type: ignore[arg-type]
        claim_ids_by_checkpoint={first: [claim]},
    )
    assert [row.instrument for row in rows] == ["z3.prove", "calc.eval"]
    assert rows[0].status == "result"
    assert rows[0].claim_ids == [claim]
    assert rows[1].status == "undecided"
    assert rows[1].claim_ids == []
    # Same inputs → same structured rows (determinism of the collector).
    again = collect_instrument_outcomes(
        interval_ids=[first, second],
        checkpoints=checkpoints,  # type: ignore[arg-type]
        claim_ids_by_checkpoint={first: [claim]},
    )
    assert [InstrumentOutcome.model_validate(r).model_dump() for r in again] == [
        InstrumentOutcome.model_validate(r).model_dump() for r in rows
    ]


def test_walk_ancestors_unknown_start_is_just_self() -> None:
    lone = uuid4()
    assert walk_ancestors(lone, {}) == {lone}
