"""The planner (0.12.1) — DB-free, network-free (real planner + injected ``StubLlm``).

Exercises the two-stage validation: a valid plan is validated & bounded; every unrunnable step is
*dropped and recorded* (never raised); a non-JSON / schema-mismatched body raises ``AgentLlmError``;
an empty plan is a valid outcome; the ``max_runs`` cap truncates with a recorded reason.
"""

import json
from uuid import uuid4

import pytest

from app.agent.llm import AgentLlmError
from app.agent.planner import plan
from app.models.enums import EvidenceGrade
from app.schemas.claim import ClaimGrounding
from app.toolbench.catalog import build_catalog
from tests.agent.stubs import StubLlm, make_claim, make_thread

CATALOG = build_catalog()  # the real production instrument catalog

# Valid inputs for two real instruments (mirrors tests/toolbench/test_instruments_write_path.py).
_CALC = {"instrument": "calc.eval", "inputs": {"expression": "1 + 1 == 2"}, "rationale": "sanity"}
_SEARCH_INPUTS = {
    "relation": "a + b == b + a",
    "variables": {"a": {"min": 1, "max": 2}, "b": {"min": 1, "max": 2}},
}


def _content(runs: list[dict]) -> str:
    return json.dumps({"runs": runs})


async def test_valid_plan_is_validated_and_bounded() -> None:
    claim = make_claim()
    runs = [
        _CALC,
        {
            "instrument": "counterexample.search",
            "inputs": _SEARCH_INPUTS,
            "claim_id": str(claim.id),
            "relation_kind": "weaken",
            "rationale": "hunt for a counterexample",
        },
    ]
    result = await plan(
        make_thread(), [claim], CATALOG, "m", llm=StubLlm(_content(runs)), max_runs=5
    )
    assert len(result.runnable) == 2
    assert result.dropped == []
    assert result.proposed_count == 2
    assert result.tokens_used == 100
    # The claim target resolves to the real UUID and the relation is carried through.
    assert result.runnable[1].claim_id == claim.id
    assert result.runnable[1].relation_kind == "weaken"


async def test_unknown_instrument_is_dropped_not_raised() -> None:
    result = await plan(
        make_thread(),
        [],
        CATALOG,
        "m",
        llm=StubLlm(_content([{"instrument": "nope.nope", "inputs": {}}])),
        max_runs=5,
    )
    assert result.runnable == []
    assert [d["reason"] for d in result.dropped] == ["unknown_instrument"]


async def test_invalid_inputs_are_dropped_with_detail() -> None:
    result = await plan(
        make_thread(),
        [],
        CATALOG,
        "m",
        llm=StubLlm(_content([{"instrument": "calc.eval", "inputs": {"wrong": 1}}])),
        max_runs=5,
    )
    assert result.runnable == []
    assert result.dropped[0]["reason"] == "invalid_inputs"
    assert result.dropped[0]["detail"]  # carries the pydantic validation error


async def test_relation_kind_without_claim_is_dropped() -> None:
    run = {
        "instrument": "calc.eval",
        "inputs": {"expression": "1 == 1"},
        "relation_kind": "support",
    }
    result = await plan(
        make_thread(), [], CATALOG, "m", llm=StubLlm(_content([run])), max_runs=5
    )
    assert result.runnable == []
    assert result.dropped[0]["reason"] == "relation_kind_without_claim"


async def test_invalid_relation_kind_is_dropped() -> None:
    claim = make_claim()
    run = {
        "instrument": "calc.eval",
        "inputs": {"expression": "1 == 1"},
        "claim_id": str(claim.id),
        "relation_kind": "bogus",
    }
    result = await plan(
        make_thread(), [claim], CATALOG, "m", llm=StubLlm(_content([run])), max_runs=5
    )
    assert result.runnable == []
    assert result.dropped[0]["reason"] == "invalid_relation_kind"


async def test_claim_not_in_the_menu_is_dropped() -> None:
    # A hallucinated claim id (not one of the offered open claims) can't be targeted.
    run = {"instrument": "calc.eval", "inputs": {"expression": "1 == 1"}, "claim_id": str(uuid4())}
    result = await plan(
        make_thread(), [], CATALOG, "m", llm=StubLlm(_content([run])), max_runs=5
    )
    assert result.runnable == []
    assert result.dropped[0]["reason"] == "unknown_claim"


async def test_non_json_raises_agent_llm_error() -> None:
    with pytest.raises(AgentLlmError):
        await plan(make_thread(), [], CATALOG, "m", llm=StubLlm("not json at all"), max_runs=5)


async def test_schema_mismatch_raises_agent_llm_error() -> None:
    # A run missing the required `instrument` is structurally invalid → whole plan rejected.
    bad = _content([{"inputs": {"expression": "1 == 1"}}])
    with pytest.raises(AgentLlmError):
        await plan(make_thread(), [], CATALOG, "m", llm=StubLlm(bad), max_runs=5)


async def test_empty_plan_is_a_valid_outcome() -> None:
    result = await plan(
        make_thread(), [], CATALOG, "m", llm=StubLlm(_content([])), max_runs=5
    )
    assert result.runnable == []
    assert result.dropped == []
    assert result.proposed_count == 0


async def test_max_runs_truncation_is_recorded() -> None:
    runs = [
        {"instrument": "calc.eval", "inputs": {"expression": f"{i} == {i}"}} for i in range(4)
    ]
    result = await plan(
        make_thread(), [], CATALOG, "m", llm=StubLlm(_content(runs)), max_runs=2
    )
    assert len(result.runnable) == 2
    assert [d["reason"] for d in result.dropped] == ["max_runs", "max_runs"]
    assert result.proposed_count == 4


async def test_markdown_fence_is_tolerated() -> None:
    fenced = f"```json\n{_content([])}\n```"
    result = await plan(make_thread(), [], CATALOG, "m", llm=StubLlm(fenced), max_runs=5)
    assert result.runnable == []


# --- 0.16.1: the grounding context reaches the model ----------------------------------------------


async def test_grounding_context_reaches_the_planning_call() -> None:
    """The wiring test: a rung passed to ``plan`` shows up in the message the LLM actually sees."""
    claim = make_claim()
    llm = StubLlm(_content([]))
    await plan(
        make_thread(),
        [claim],
        CATALOG,
        "m",
        llm=llm,
        max_runs=5,
        grounding={claim.id: ClaimGrounding(support=EvidenceGrade.B, headline="B")},
    )
    user_message = llm.calls[0]["messages"][1]["content"]
    assert "grounding: B" in user_message
    assert "to raise: run one of [z3.prove]" in user_message


async def test_grounding_is_optional_and_omitting_it_changes_no_validation() -> None:
    """Read-only context: without it every claim reads ``ungrounded``, but the plan is unaffected.

    Keeps the 0.12.1 guarantee intact — nothing the model returns can set a grade, and the two-stage
    validation is identical with or without the new argument.
    """
    claim = make_claim()
    runs = [{"instrument": "calc.eval", "inputs": {"expression": "1 + 1 == 2"}}]
    without = await plan(
        make_thread(), [claim], CATALOG, "m", llm=StubLlm(_content(runs)), max_runs=5
    )
    with_grounding = await plan(
        make_thread(),
        [claim],
        CATALOG,
        "m",
        llm=StubLlm(_content(runs)),
        max_runs=5,
        grounding={claim.id: ClaimGrounding(support=EvidenceGrade.A, headline="proven")},
    )
    assert len(without.runnable) == len(with_grounding.runnable) == 1
    assert without.dropped == with_grounding.dropped == []
