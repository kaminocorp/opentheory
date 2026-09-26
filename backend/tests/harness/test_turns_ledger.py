"""DB-backed harness turn metering — debit, exhaust, mint-through-MCP.

Skips without TEST_DATABASE_URL (same gate as the rest of the ledger suite).
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import httpx
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.harness.gateway import DEFAULT_MODEL, GatewayClient
from app.harness.turns import (
    REASON_PROJECT_BUDGET,
    TURN_NOTES,
    supervise_turn,
)
from app.models.checkpoint import Checkpoint
from app.models.compute_debit import ComputeDebit
from app.models.enums import ComputeDebitKind, ComputeDebitRateSource
from app.services.compute import BUDGET_EXHAUSTED
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
    async with session_factory() as session:
        result = await session.execute(
            select(ComputeDebit).where(ComputeDebit.project_id == UUID(project_id))
        )
        return list(result.scalars().all())


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
