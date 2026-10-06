"""DB-backed harness turn metering — debit, exhaust, mint-through-MCP.

Skips without TEST_DATABASE_URL (same gate as the rest of the ledger suite).
"""

from __future__ import annotations

import json
from decimal import Decimal
from uuid import UUID

import httpx
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.harness.gateway import DEFAULT_MODEL, GatewayClient
from app.harness.session import (
    REASON_NOT_MEMBER,
    HarnessSession,
    TurnRefused,
    is_daily_cap_adjustment,
    unmatched_holds,
)
from app.harness.turns import (
    REASON_PROJECT_BUDGET,
    TURN_NOTES,
    supervise_turn,
)
from app.models.actor import Actor
from app.models.checkpoint import Checkpoint
from app.models.compute_debit import ComputeDebit
from app.models.contribution import Contribution
from app.models.enums import ActorType, ComputeDebitKind, ComputeDebitRateSource, ProjectRole
from app.models.funding import FundingAllocation
from app.models.project_member import ProjectMember
from app.services.compute import BUDGET_EXHAUSTED
from app.services.harness_meter import load_today_adjustments
from tests.principals import create_owned_project, make_dev_principal

_OK_BODY = {
    "choices": [{"message": {"content": "use calc.eval"}}],
    "usage": {"total_tokens": 20, "prompt_tokens": 15, "completion_tokens": 5},
}


def _gateway(handler) -> GatewayClient:
    return GatewayClient(
        api_key="sk-test",
        base_url="https://openrouter.ai/api/v1",
        transport=httpx.MockTransport(handler),
    )


async def _checkpoint_count(session_factory: async_sessionmaker, project_id: str) -> int:
    async with session_factory() as session:
        result = await session.execute(
            select(func.count())
            .select_from(Checkpoint)
            .where(Checkpoint.project_id == UUID(project_id))
        )
        return int(result.scalar_one())


async def _debit_rows(session_factory: async_sessionmaker, project_id: str) -> list[ComputeDebit]:
    """Billed spend only — daily-cap hold/release rows are not pot debits."""
    async with session_factory() as session:
        result = await session.execute(
            select(ComputeDebit).where(ComputeDebit.project_id == UUID(project_id))
        )
        return [
            row
            for row in result.scalars().all()
            if row.tokens_used > 0 and not is_daily_cap_adjustment(row.notes)
        ]


async def _hold_rows(session_factory: async_sessionmaker, project_id: str) -> list:
    async with session_factory() as session:
        return await load_today_adjustments(session, UUID(project_id))


async def test_successful_turn_debits_and_lands_instrument(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await make_dev_principal(client, display_name="Ada", roles=("internal",))
    project_id = await create_owned_project(client, actor_id, "harness-turn-ok")
    funded = await client.post(
        f"/api/v1/projects/{project_id}/funding",
        json={"amount": "10.00", "currency": "USD", "kind": "top_up", "source": "native"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert funded.status_code == 201, funded.text
    before = await _checkpoint_count(session_factory, project_id)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_OK_BODY)

    result = await supervise_turn(
        messages=[{"role": "user", "content": "evaluate 1+1"}],
        project_id=project_id,
        gateway=_gateway(handler),
        session_factory=session_factory,
        actor_env={"OPENTHEORY_DEV_ACTOR_ID": actor_id},
        mcp_call={
            "name": "run_instrument",
            "arguments": {
                "project_id": project_id,
                "name": "calc.eval",
                "input": {"expression": "1 + 1"},
            },
        },
    )

    assert result.ok is True
    assert result.refused is False
    assert result.tokens_used == 20
    assert result.debit_recorded is True
    assert result.minted is True
    assert result.checkpoint_id
    assert result.mcp is not None
    assert result.mcp["status"] == "result"
    assert await _checkpoint_count(session_factory, project_id) == before + 1

    debits = await _debit_rows(session_factory, project_id)
    assert len(debits) == 1
    assert debits[0].tokens_used == 20
    assert debits[0].prompt_tokens == 15
    assert debits[0].completion_tokens == 5
    assert debits[0].agent_run_id is None
    assert debits[0].kind is ComputeDebitKind.PLANNING
    assert debits[0].model == DEFAULT_MODEL
    assert TURN_NOTES in (debits[0].notes or "")
    assert hasattr(ComputeDebit, "actor_id")
    assert str(debits[0].actor_id) == actor_id

    async with session_factory() as session:
        author = await session.get(Actor, UUID(actor_id))
        assert author is not None
        assert author.type is ActorType.HUMAN
        checkpoint = await session.get(Checkpoint, UUID(result.checkpoint_id))
        assert checkpoint is not None
        assert str(checkpoint.author_id) == actor_id
        assert checkpoint.sponsored_by_actor_id is None
        contrib = (
            await session.execute(
                select(Contribution).where(
                    Contribution.checkpoint_id == UUID(result.checkpoint_id)
                )
            )
        ).scalar_one()
        assert str(contrib.actor_id) == actor_id
        allocations = (
            await session.execute(
                select(FundingAllocation).where(
                    FundingAllocation.project_id == UUID(project_id)
                )
            )
        ).scalars().all()
        assert len(allocations) == 1
        assert allocations[0].account_id == author.account_id
        assert allocations[0].amount == Decimal("10.00")


async def test_attempted_turn_debits_and_mints_nothing(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await make_dev_principal(client, display_name="Bea", roles=("internal",))
    project_id = await create_owned_project(client, actor_id, "harness-turn-fail")
    funded = await client.post(
        f"/api/v1/projects/{project_id}/funding",
        json={"amount": "10.00", "currency": "USD", "kind": "top_up", "source": "native"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert funded.status_code == 201, funded.text
    before = await _checkpoint_count(session_factory, project_id)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "  "}}],
                "usage": {"total_tokens": 9, "prompt_tokens": 8, "completion_tokens": 1},
            },
        )

    result = await supervise_turn(
        messages=[{"role": "user", "content": "hi"}],
        project_id=project_id,
        gateway=_gateway(handler),
        session_factory=session_factory,
        actor_env={"OPENTHEORY_DEV_ACTOR_ID": actor_id},
        mcp_call={
            "name": "run_instrument",
            "arguments": {
                "project_id": project_id,
                "name": "calc.eval",
                "input": {"expression": "1 + 1"},
            },
        },
    )

    assert result.ok is False
    assert result.refused is False
    assert result.tokens_used == 9
    assert result.debit_recorded is True
    assert result.minted is False
    assert result.checkpoint_id is None
    assert await _checkpoint_count(session_factory, project_id) == before
    debits = await _debit_rows(session_factory, project_id)
    assert len(debits) == 1
    assert debits[0].tokens_used == 9


async def test_exhausted_budget_refuses_without_debit_or_mint(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await make_dev_principal(
        client, display_name="Funder", roles=("internal",)
    )
    project_id = await create_owned_project(client, actor_id, "harness-turn-broke")
    funded = await client.post(
        f"/api/v1/projects/{project_id}/funding",
        json={"amount": "10.00", "currency": "USD", "kind": "top_up", "source": "native"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert funded.status_code == 201, funded.text

    async with session_factory() as session:
        session.add(
            ComputeDebit(
                project_id=UUID(project_id),
                tokens_used=1_000,
                amount=Decimal("10"),
                currency="USD",
                rate_per_1k=Decimal("10"),
                rate_source=ComputeDebitRateSource.BLENDED_FALLBACK,
                kind=ComputeDebitKind.PLANNING,
            )
        )
        await session.commit()

    before = await _checkpoint_count(session_factory, project_id)

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("exhausted pot must refuse before the LLM call")

    result = await supervise_turn(
        messages=[{"role": "user", "content": "hi"}],
        project_id=project_id,
        gateway=_gateway(handler),
        session_factory=session_factory,
        actor_env={"OPENTHEORY_DEV_ACTOR_ID": actor_id},
        mcp_call={
            "name": "run_instrument",
            "arguments": {
                "project_id": project_id,
                "name": "calc.eval",
                "input": {"expression": "1 + 1"},
            },
        },
    )

    assert result.refused is True
    assert result.reason in {REASON_PROJECT_BUDGET, BUDGET_EXHAUSTED}
    assert result.tokens_used == 0
    assert result.debit_recorded is False
    assert result.minted is False
    assert await _checkpoint_count(session_factory, project_id) == before
    # The seed debit is the only row — the refused turn wrote nothing.
    assert len(await _debit_rows(session_factory, project_id)) == 1


async def test_supervise_turn_sends_clamped_max_tokens_and_returns_clamp(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await make_dev_principal(client, display_name="Clamp", roles=("internal",))
    project_id = await create_owned_project(client, actor_id, "harness-turn-clamp")
    seen: dict[str, int | None] = {"max_tokens": None}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen["max_tokens"] = body.get("max_tokens")
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"total_tokens": 80, "prompt_tokens": 30, "completion_tokens": 50},
            },
        )

    result = await supervise_turn(
        messages=[{"role": "user", "content": "hi"}],
        project_id=project_id,
        gateway=_gateway(handler),
        session_factory=session_factory,
        actor_env={"OPENTHEORY_DEV_ACTOR_ID": actor_id},
        max_tokens=64,
        env={"OPENTHEORY_HARNESS_DAILY_TOKEN_CAP": "40"},
    )

    assert result.ok is True
    assert result.refused is False
    assert seen["max_tokens"] == 40
    assert result.clamp == 40
    assert result.overshoot == 40
    assert result.tokens_used == 80
    assert result.price_known is False
    debits = await _debit_rows(session_factory, project_id)
    assert len(debits) == 1
    notes = debits[0].notes or ""
    assert "clamp=40" in notes
    assert "overshoot=40" in notes
    assert "pot_room=none" in notes


async def test_member_actor_env_is_allowed(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    """A current member may authorize: hold, provider call, debit when tokens moved."""
    actor_id = await make_dev_principal(client, display_name="Member", roles=("internal",))
    project_id = await create_owned_project(client, actor_id, "harness-turn-member")
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json=_OK_BODY)

    result = await supervise_turn(
        messages=[{"role": "user", "content": "hi"}],
        project_id=project_id,
        gateway=_gateway(handler),
        session_factory=session_factory,
        actor_env={"OPENTHEORY_DEV_ACTOR_ID": actor_id},
    )

    assert result.ok is True
    assert result.refused is False
    assert result.tokens_used == 20
    assert result.debit_recorded is True
    assert result.minted is False
    assert calls["n"] == 1
    assert len(await _debit_rows(session_factory, project_id)) == 1
    holds = await _hold_rows(session_factory, project_id)
    assert any(row.tokens_used > 0 for row in holds)
    assert any(row.tokens_used < 0 for row in holds)


async def test_outsider_actor_env_refuses_without_hold_debit_or_provider(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    """0.52.0: spend fails closed unless the acting actor is a current member."""
    owner_id = await make_dev_principal(client, display_name="Owner", roles=("internal",))
    outsider_id = await make_dev_principal(client, display_name="Eve")
    project_id = await create_owned_project(client, owner_id, "harness-turn-outsider")
    funded = await client.post(
        f"/api/v1/projects/{project_id}/funding",
        json={"amount": "10.00", "currency": "USD", "kind": "top_up", "source": "native"},
        headers={"X-Dev-Actor-Id": owner_id},
    )
    assert funded.status_code == 201, funded.text
    before = await _checkpoint_count(session_factory, project_id)

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("non-member must refuse before the LLM call")

    result = await supervise_turn(
        messages=[{"role": "user", "content": "evaluate 1+1"}],
        project_id=project_id,
        gateway=_gateway(handler),
        session_factory=session_factory,
        actor_env={"OPENTHEORY_DEV_ACTOR_ID": outsider_id},
        mcp_call={
            "name": "run_instrument",
            "arguments": {
                "project_id": project_id,
                "name": "calc.eval",
                "input": {"expression": "1 + 1"},
            },
        },
    )

    assert result.ok is False
    assert result.refused is True
    assert result.reason == REASON_NOT_MEMBER
    assert result.tokens_used == 0
    assert result.debit_recorded is False
    assert result.minted is False
    assert result.checkpoint_id is None
    assert result.mcp is None
    assert await _checkpoint_count(session_factory, project_id) == before
    assert await _debit_rows(session_factory, project_id) == []
    assert await _hold_rows(session_factory, project_id) == []

    async with session_factory() as session:
        owner = await session.get(Actor, UUID(owner_id))
        assert owner is not None
        allocations = (
            await session.execute(
                select(FundingAllocation).where(
                    FundingAllocation.project_id == UUID(project_id)
                )
            )
        ).scalars().all()
        assert len(allocations) == 1
        assert allocations[0].account_id == owner.account_id
        assert allocations[0].amount == Decimal("10.00")


async def test_accountless_research_crew_actor_refuses_spend(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    """Un-rostered Research crew still cannot authorize spend (0.51.1 / 0.54.0 pin).

    Inserted raw so ``get_or_create`` cannot heal a roster row onto it.
    """
    owner_id = await make_dev_principal(client, display_name="Owner", roles=("internal",))
    project_id = await create_owned_project(client, owner_id, "harness-turn-agent")
    before = await _checkpoint_count(session_factory, project_id)

    async with session_factory() as session:
        agent = Actor(
            type=ActorType.AGENT,
            display_name="Research crew",
            account_id=None,
            actor_metadata={"project_id": project_id},
        )
        session.add(agent)
        await session.commit()
        agent_id = str(agent.id)
        assert agent.account_id is None
        assert agent.type is ActorType.AGENT

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("un-rostered agent must refuse before the LLM call")

    result = await supervise_turn(
        messages=[{"role": "user", "content": "hi"}],
        project_id=project_id,
        gateway=_gateway(handler),
        session_factory=session_factory,
        actor_env={"OPENTHEORY_DEV_ACTOR_ID": agent_id},
    )

    assert result.refused is True
    assert result.reason == REASON_NOT_MEMBER
    assert result.tokens_used == 0
    assert result.debit_recorded is False
    assert result.minted is False
    assert await _checkpoint_count(session_factory, project_id) == before
    assert await _debit_rows(session_factory, project_id) == []
    assert await _hold_rows(session_factory, project_id) == []


async def test_removed_member_refuses_next_authorize_mid_turn_spend_stands(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    """Membership is a start-of-turn gate. Removal mid-turn does not drop the debit.

    A collaborator who is a current member may authorize. If they are
    removed after the hold (mid-turn), ``record_spend`` still converts
    and bills tokens that moved — pot honesty. The next authorize
    fails closed: no hold, no debit, no provider call.
    """
    owner_id = await make_dev_principal(client, display_name="Owner", roles=("internal",))
    collab_id = await make_dev_principal(client, display_name="Collab")
    project_id = await create_owned_project(client, owner_id, "harness-turn-removed")

    async with session_factory() as session:
        owner = await session.get(Actor, UUID(owner_id))
        collab = await session.get(Actor, UUID(collab_id))
        assert owner is not None and collab is not None
        assert collab.account_id is not None
        session.add(
            ProjectMember(
                project_id=UUID(project_id),
                account_id=collab.account_id,
                role=ProjectRole.ADMIN,
                invited_by_account_id=owner.account_id,
            )
        )
        await session.commit()
        collab_account_id = str(collab.account_id)

    owner_session = HarnessSession(
        project_id=project_id,
        session_factory=session_factory,
        actor_env={"OPENTHEORY_DEV_ACTOR_ID": collab_id},
    )
    hold = await owner_session.authorize()
    assert hold is not None
    assert hold.tokens > 0
    assert len(await _hold_rows(session_factory, project_id)) == 1

    removed = await client.delete(
        f"/api/v1/projects/{project_id}/members/{collab_account_id}",
        headers={"X-Dev-Actor-Id": owner_id},
    )
    assert removed.status_code == 204, removed.text

    spent = await owner_session.record_spend(
        tokens_used=20,
        model=DEFAULT_MODEL,
        prompt_tokens=15,
        completion_tokens=5,
        hold=hold,
    )
    assert spent is True
    debits = await _debit_rows(session_factory, project_id)
    assert len(debits) == 1
    assert debits[0].tokens_used == 20
    assert str(debits[0].actor_id) == collab_id

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("removed member must refuse before the LLM call")

    result = await supervise_turn(
        messages=[{"role": "user", "content": "hi"}],
        project_id=project_id,
        gateway=_gateway(handler),
        session_factory=session_factory,
        actor_env={"OPENTHEORY_DEV_ACTOR_ID": collab_id},
    )
    assert result.refused is True
    assert result.reason == REASON_NOT_MEMBER
    assert result.tokens_used == 0
    assert result.debit_recorded is False
    assert len(await _debit_rows(session_factory, project_id)) == 1
    later = HarnessSession(
        project_id=project_id,
        session_factory=session_factory,
        actor_env={"OPENTHEORY_DEV_ACTOR_ID": collab_id},
    )
    try:
        await later.authorize()
        raise AssertionError("removed member must not take a hold")
    except TurnRefused as exc:
        assert exc.reason == REASON_NOT_MEMBER
    # Convert already released the mid-turn hold; the refused authorize wrote none.
    assert unmatched_holds(await _hold_rows(session_factory, project_id)) == []
