"""The ``AgentRun`` read contract for the yield measure (0.16.2, DB-free).

One distinction is load-bearing and easy to lose: **"never measured" is not "measured zero"**. A
pass that failed before it could measure, and a pass that examined four claims and moved none, are
different statements about what happened, and the surfaces render them differently (``—`` vs
``0/4``). The column cannot express that on its own — its ``'{}'`` server default and a genuine
zero measure are both dicts — so the read schema is where the two are separated.

0.16.1 shipped this as a non-optional field defaulted to an empty ``PassYield``, which collapsed the
two: the client's ``measure !== undefined`` guard could never be false, and a pre-0.16.1 row read as
"no open claims to move" — a sentence about a thread nobody had looked at.
"""

from datetime import UTC, datetime
from uuid import uuid4

from app.models.enums import AgentRunStatus
from app.schemas.agent_run import AgentRunSummary, PassYield


def _row(**overrides):
    """The minimum an ``AgentRunSummary`` needs, as the ORM row would present it."""
    now = datetime.now(UTC)
    return {
        "id": uuid4(),
        "project_id": uuid4(),
        "thread_id": uuid4(),
        "branch_id": None,
        "agent_actor_id": None,
        "triggered_by_actor_id": uuid4(),
        "role": "researcher",
        "model": "openai/gpt-4o-mini",
        "status": AgentRunStatus.COMPLETED,
        "planned_count": 1,
        "ran_count": 1,
        "tokens_used": 10,
        "grounding_yield": {},
        "error": None,
        "created_at": now,
        "updated_at": now,
        **overrides,
    }


def test_an_empty_column_reads_as_never_measured() -> None:
    """The ``'{}'`` server default — a pre-0.16.1 row, or a pass that failed before measuring."""
    assert AgentRunSummary.model_validate(_row()).grounding_yield is None


def test_a_genuine_zero_measure_survives_as_a_measure() -> None:
    """Looked at four claims, moved none. That is a *result*, and must not degrade to ``None``.

    ``compute_yield`` always writes all three keys, which is exactly what distinguishes it from the
    column default — the whole tri-state rests on this staying true.
    """
    measured = AgentRunSummary.model_validate(
        _row(grounding_yield={"measured": 4, "moved": 0, "changed": []})
    ).grounding_yield

    assert measured == PassYield(measured=4, moved=0, changed=[])


def test_compute_yield_never_serializes_to_the_empty_marker() -> None:
    """Guards the invariant the tri-state depends on: no real measure can look like "unmeasured"."""
    assert PassYield().model_dump(mode="json") != {}


def test_a_recorded_movement_round_trips_through_the_read_model() -> None:
    claim_id = uuid4()
    summary = AgentRunSummary.model_validate(
        _row(
            grounding_yield={
                "measured": 1,
                "moved": 1,
                "changed": [
                    {
                        "claim_id": str(claim_id),
                        "before": "proven",
                        "after": "refuted",
                        "movement": "settled",
                    }
                ],
            }
        )
    )

    assert summary.grounding_yield is not None
    entry = summary.grounding_yield.changed[0]
    assert entry.claim_id == claim_id
    assert (entry.before, entry.after, entry.movement) == ("proven", "refuted", "settled")
