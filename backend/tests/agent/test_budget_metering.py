"""Project-budget metering (0.19.0) — DB-backed (skips without ``TEST_DATABASE_URL``).

Proves the three acceptance bars: available drops after a pass by the metered amount; an
exhausted project refuses to start (failed trace, mints nothing); a pass that exhausts the
remainder mid-way skips remaining instrument runs with ``budget_exhausted`` and mints
nothing further. Also: the funding read model matches the debit ledger, the agent never
funds, and ``ComputeDebit`` is append-only.
"""

from decimal import Decimal
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agent.planner import PlannedRun, PlanResult
from app.core.config import settings
from app.models import AppendOnlyError
from app.models.agent_run import AgentRun
from app.models.checkpoint import Checkpoint
from app.models.compute_debit import ComputeDebit
from app.models.contribution import Contribution
from app.models.enums import (
    AgentRunStatus,
    ComputeDebitKind,
    ComputeDebitRateSource,
    FundingKind,
    FundingSource,
    FundingStatus,
)
from app.models.funding import FundingAllocation
from app.models.project import Project
from app.models.validation import Validation
from app.services.agent_runs import run_agent_pass
from app.services.compute import tokens_to_cost

_RATE = Decimal("1.00")


async def _actor(client: AsyncClient, name: str = "Ada") -> str:
    from tests.principals import make_dev_principal

    return await make_dev_principal(client, display_name=name)


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


async def _thread_checkpoint(
    client: AsyncClient, project_id: str, thread_id: str, actor_id: str
) -> None:
    resp = await client.post(
        f"/api/v1/projects/{project_id}/checkpoints",
        json={"summary": "seed", "thread_id": thread_id},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert resp.status_code == 201, resp.text


async def _assign_model(session_factory: async_sessionmaker, project_id: str) -> None:
    async with session_factory() as session:
        project = await session.get(Project, UUID(project_id))
        project.agent_models = {"researcher": "anthropic/claude-sonnet-4"}
        await session.commit()


async def _grant_budget(
    session_factory: async_sessionmaker, project_id: str, *, amount: str
) -> None:
    async with session_factory() as session:
        session.add(
            FundingAllocation(
                project_id=UUID(project_id),
                amount=Decimal(amount),
                currency="USD",
                kind=FundingKind.TOP_UP,
                source=FundingSource.NATIVE,
                status=FundingStatus.SETTLED,
            )
        )
        await session.commit()


async def _make_run(
    session_factory: async_sessionmaker, project_id: str, thread_id: str, actor_id: str
) -> UUID:
    async with session_factory() as session:
        agent_run = AgentRun(
            project_id=UUID(project_id),
            thread_id=UUID(thread_id),
            triggered_by_actor_id=UUID(actor_id),
            role="researcher",
            status=AgentRunStatus.RUNNING,
        )
        session.add(agent_run)
        await session.commit()
        return agent_run.id


def _stub_planner(plan_result: PlanResult):
    """One-shot stub: return ``plan_result`` once, then empty.

    0.20.0 will replan unless the second call is empty. An always-same plan would
    re-execute and break ``ran_count`` / ``tokens_used`` / ``skipped==2`` assertions.
    """
    calls = {"n": 0}

    async def _planner(
        thread, open_claims, catalog, model, *, llm, max_runs, grounding=None,
        observations=None, signals=None,
    ):
        calls["n"] += 1
        if calls["n"] == 1:
            return plan_result
        return PlanResult(runnable=[], proposed_count=0, tokens_used=0)

    return _planner


def _one_calc(*, tokens_used: int) -> PlanResult:
    return PlanResult(
        runnable=[PlannedRun(instrument="calc.eval", inputs={"expression": "1 == 1"})],
        proposed_count=1,
        tokens_used=tokens_used,
    )


def _dec(value) -> Decimal:
    return Decimal(str(value))


@pytest.fixture
def unit_rate(monkeypatch: pytest.MonkeyPatch) -> Decimal:
    """$1 / 1k tokens so 42 tokens is a visible $0.042 debit."""
    monkeypatch.setattr(settings, "agent_token_rate_usd_per_1k", _RATE)
    return _RATE


async def test_available_drops_after_a_pass_by_the_metered_amount(
    client: AsyncClient, session_factory: async_sessionmaker, unit_rate: Decimal
) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client, "budget-drop", actor_id=actor_id)
    thread_id = await _thread(client, project_id, actor_id)
    await _thread_checkpoint(client, project_id, thread_id, actor_id)
    await _assign_model(session_factory, project_id)
    await _grant_budget(session_factory, project_id, amount="10.00")
    run_id = await _make_run(session_factory, project_id, thread_id, actor_id)

    before = (await client.get(f"/api/v1/projects/{project_id}/budget")).json()
    assert _dec(before["funded"]) == Decimal("10.00")
    assert _dec(before["spent"]) == Decimal("0")
    assert _dec(before["available"]) == Decimal("10.00")

    tokens = 42
    expected = tokens_to_cost(tokens, unit_rate)

    async with session_factory() as session:
        result = await run_agent_pass(
            session, run_id, planner=_stub_planner(_one_calc(tokens_used=tokens))
        )
        assert result.status is AgentRunStatus.COMPLETED
        assert result.tokens_used == tokens
        assert result.ran_count == 1

    after = (await client.get(f"/api/v1/projects/{project_id}/budget")).json()
    assert _dec(after["funded"]) == Decimal("10.00")
    assert _dec(after["spent"]) == expected
    assert _dec(after["available"]) == Decimal("10.00") - expected

    overview = (await client.get(f"/api/v1/projects/{project_id}/overview")).json()
    assert _dec(overview["budget"]["spent"]) == expected
    assert _dec(overview["budget"]["available"]) == Decimal("10.00") - expected

    async with session_factory() as session:
        debits = list((await session.execute(select(ComputeDebit))).scalars())
        assert len(debits) == 1
        assert debits[0].tokens_used == tokens
        assert debits[0].amount == expected
        assert debits[0].kind is ComputeDebitKind.PLANNING
        assert debits[0].rate_source is ComputeDebitRateSource.BLENDED_FALLBACK
        assert debits[0].notes is not None and "rate fallback:" in debits[0].notes
        assert str(debits[0].agent_run_id) == str(run_id)
        # The agent did not become a funder.
        funds = list(
            (await session.execute(select(Contribution).where(Contribution.action == "fund")))
            .scalars()
        )
        assert funds == []


async def test_exhausted_budget_refuses_to_start_and_mints_nothing(
    client: AsyncClient, session_factory: async_sessionmaker, unit_rate: Decimal
) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client, "budget-empty", actor_id=actor_id)
    thread_id = await _thread(client, project_id, actor_id)
    await _thread_checkpoint(client, project_id, thread_id, actor_id)
    await _assign_model(session_factory, project_id)
    # No funding — available is 0.
    run_id = await _make_run(session_factory, project_id, thread_id, actor_id)

    called = {"planner": False}

    async def _boom(
        thread, open_claims, catalog, model, *, llm, max_runs, grounding=None,
        observations=None, signals=None,
    ):
        called["planner"] = True
        raise AssertionError("planner must not run when the project budget is exhausted")

    async with session_factory() as session:
        result = await run_agent_pass(session, run_id, planner=_boom)
        assert result.status is AgentRunStatus.FAILED
        assert result.error == "project budget exhausted"
        assert result.ran_count == 0
        assert result.tokens_used == 0

    assert called["planner"] is False

    budget = (await client.get(f"/api/v1/projects/{project_id}/budget")).json()
    assert _dec(budget["spent"]) == Decimal("0")
    assert _dec(budget["available"]) == Decimal("0")

    async with session_factory() as session:
        assert list((await session.execute(select(ComputeDebit))).scalars()) == []
        tool_runs = list(
            (await session.execute(select(Contribution).where(Contribution.action == "tool_run")))
            .scalars()
        )
        assert tool_runs == []
        # Seed checkpoint is the only mint — the refused pass added nothing.
        checkpoints = list((await session.execute(select(Checkpoint))).scalars())
        assert len(checkpoints) == 1


async def test_mid_pass_stop_skips_remaining_runs_when_planning_exhausts_the_remainder(
    client: AsyncClient, session_factory: async_sessionmaker, unit_rate: Decimal
) -> None:
    """Fund just enough to *start*, but not enough to cover the planning tokens.

    The planner still runs (available was > 0); the debit records the spend; every
    instrument step is skipped with ``budget_exhausted``; no branch is forked.
    """
    actor_id = await _actor(client)
    project_id = await _project(client, "budget-mid", actor_id=actor_id)
    thread_id = await _thread(client, project_id, actor_id)
    await _thread_checkpoint(client, project_id, thread_id, actor_id)
    await _assign_model(session_factory, project_id)
    await _grant_budget(session_factory, project_id, amount="0.02")  # 20 tokens at $1/1k
    run_id = await _make_run(session_factory, project_id, thread_id, actor_id)

    plan = PlanResult(
        runnable=[
            PlannedRun(instrument="calc.eval", inputs={"expression": "1 == 1"}, rationale="a"),
            PlannedRun(instrument="calc.eval", inputs={"expression": "2 == 2"}, rationale="b"),
        ],
        proposed_count=2,
        tokens_used=50,  # $0.05 > $0.02 funded
    )

    async with session_factory() as session:
        result = await run_agent_pass(session, run_id, planner=_stub_planner(plan))
        assert result.status is AgentRunStatus.COMPLETED
        assert result.ran_count == 0
        assert result.branch_id is None
        skipped = [s for s in result.steps if s["status"] == "skipped"]
        assert len(skipped) == 2
        assert {s["reason"] for s in skipped} == {"budget_exhausted"}

    budget = (await client.get(f"/api/v1/projects/{project_id}/budget")).json()
    assert _dec(budget["spent"]) == tokens_to_cost(50, unit_rate)
    assert _dec(budget["available"]) == Decimal("0.02") - tokens_to_cost(50, unit_rate)

    async with session_factory() as session:
        tool_runs = list(
            (await session.execute(select(Contribution).where(Contribution.action == "tool_run")))
            .scalars()
        )
        assert tool_runs == []


async def test_agent_pass_never_writes_a_funding_allocation_or_validation(
    client: AsyncClient, session_factory: async_sessionmaker, unit_rate: Decimal
) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client, "budget-roles", actor_id=actor_id)
    thread_id = await _thread(client, project_id, actor_id)
    await _thread_checkpoint(client, project_id, thread_id, actor_id)
    await _assign_model(session_factory, project_id)
    await _grant_budget(session_factory, project_id, amount="10.00")
    run_id = await _make_run(session_factory, project_id, thread_id, actor_id)

    async with session_factory() as session:
        await run_agent_pass(
            session, run_id, planner=_stub_planner(_one_calc(tokens_used=10))
        )

    async with session_factory() as session:
        allocations = list((await session.execute(select(FundingAllocation))).scalars())
        assert len(allocations) == 1  # the grant we inserted, nothing from the pass
        assert allocations[0].kind is FundingKind.TOP_UP
        assert list((await session.execute(select(Validation))).scalars()) == []
        actions = {
            c.action
            for c in (await session.execute(select(Contribution))).scalars()
        }
        assert "fund" not in actions
        assert "validate" not in actions
        assert "tool_run" in actions  # the agent contributed


async def test_compute_debit_is_append_only(
    client: AsyncClient, session_factory: async_sessionmaker, unit_rate: Decimal
) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client, "budget-append", actor_id=actor_id)
    thread_id = await _thread(client, project_id, actor_id)
    await _assign_model(session_factory, project_id)
    await _grant_budget(session_factory, project_id, amount="10.00")
    run_id = await _make_run(session_factory, project_id, thread_id, actor_id)

    async with session_factory() as session:
        await run_agent_pass(
            session, run_id, planner=_stub_planner(_one_calc(tokens_used=10))
        )

    async with session_factory() as session:
        debit = (await session.execute(select(ComputeDebit))).scalar_one()
        debit.notes = "amended"
        with pytest.raises(AppendOnlyError, match="append-only"):
            await session.flush()

    async with session_factory() as session:
        debit = (await session.execute(select(ComputeDebit))).scalar_one()
        debit_id = debit.id
        await session.delete(debit)
        with pytest.raises(AppendOnlyError):
            await session.flush()

    async with session_factory() as session:
        assert await session.get(ComputeDebit, debit_id) is not None


async def test_debit_is_idempotent_for_the_same_pass(
    client: AsyncClient, session_factory: async_sessionmaker, unit_rate: Decimal
) -> None:
    from app.services.compute import record_compute_debit

    actor_id = await _actor(client)
    project_id = await _project(client, "budget-once", actor_id=actor_id)
    thread_id = await _thread(client, project_id, actor_id)
    await _assign_model(session_factory, project_id)
    await _grant_budget(session_factory, project_id, amount="10.00")
    run_id = await _make_run(session_factory, project_id, thread_id, actor_id)

    async with session_factory() as session:
        await run_agent_pass(
            session, run_id, planner=_stub_planner(_one_calc(tokens_used=20))
        )

    async with session_factory() as session:
        again = await record_compute_debit(
            session,
            project_id=UUID(project_id),
            agent_run_id=run_id,
            tokens_used=20,
            model="anthropic/claude-sonnet-4",
        )
        assert again is not None
        again_id = again.id
        await session.commit()

    async with session_factory() as session:
        rows = list((await session.execute(select(ComputeDebit))).scalars())
        assert len(rows) == 1
        assert rows[0].id == again_id
