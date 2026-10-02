"""DB-backed session-owner metering — the path dsh → gateway actually runs.

Skips without TEST_DATABASE_URL (same gate as the rest of the ledger suite).
"""

from __future__ import annotations

import json
from decimal import Decimal
from uuid import UUID

import httpx
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.harness.campaign import QUESTION, TITLE, create_metered_gateway_app, open_session
from app.harness.gateway import DEFAULT_MODEL, GATEWAY_TOKEN_ENV, GatewayClient
from app.harness.live_mcp import invoke
from app.harness.session import (
    REASON_PROJECT_BUDGET,
    SESSION_NOTES,
    HarnessSession,
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


async def _complete(
    app,
    *,
    token: str = "gw-secret",
) -> httpx.Response:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://gw") as client:
        return await client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "model": DEFAULT_MODEL,
                "messages": [{"role": "user", "content": "hi"}],
                "models": ["openai/gpt-4o"],
                "route": "fallback",
            },
        )


async def test_exhausted_funded_project_does_not_call_model_or_mint(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await make_dev_principal(client, display_name="Funder", roles=("internal",))
    project_id = await create_owned_project(
        client, actor_id, "session-exhausted", title=TITLE, question=QUESTION
    )
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

    owner = open_session(project_id, session_factory=session_factory)
    app = create_metered_gateway_app(
        owner,
        env={GATEWAY_TOKEN_ENV: "gw-secret"},
        gateway=_gateway(handler),
    )
    refused = await _complete(app)
    assert refused.status_code == 422
    payload = refused.json()
    assert payload["refused"] is True
    assert payload["error"] in {REASON_PROJECT_BUDGET, BUDGET_EXHAUSTED}
    assert payload["tokens_used"] == 0
    assert payload["minted"] is False
    assert await _checkpoint_count(session_factory, project_id) == before
    assert len(await _debit_rows(session_factory, project_id)) == 1

    mcp = await invoke(
        "run_instrument",
        {
            "project_id": project_id,
            "name": "calc.eval",
            "input": {"expression": "1 + 1"},
        },
        session_factory=session_factory,
        env={"OPENTHEORY_DEV_ACTOR_ID": actor_id},
    )
    assert mcp["ok"] is False
    assert mcp["minted"] is False
    assert await _checkpoint_count(session_factory, project_id) == before


async def test_successful_gateway_turn_debits_only_when_tokens_moved(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await make_dev_principal(client, display_name="Ada", roles=("internal",))
    project_id = await create_owned_project(
        client, actor_id, "session-debit", title=TITLE, question=QUESTION
    )
    funded = await client.post(
        f"/api/v1/projects/{project_id}/funding",
        json={"amount": "10.00", "currency": "USD", "kind": "top_up", "source": "native"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert funded.status_code == 201, funded.text
    before = await _checkpoint_count(session_factory, project_id)

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert "models" not in body
        assert "route" not in body
        assert body["provider"]["allow_fallbacks"] is False
        return httpx.Response(200, json=_OK_BODY)

    owner = open_session(project_id, session_factory=session_factory)
    app = create_metered_gateway_app(
        owner,
        env={GATEWAY_TOKEN_ENV: "gw-secret"},
        gateway=_gateway(handler),
    )
    ok = await _complete(app)
    assert ok.status_code == 200, ok.text
    assert ok.json()["usage"]["total_tokens"] == 20
    assert await _checkpoint_count(session_factory, project_id) == before

    debits = await _debit_rows(session_factory, project_id)
    assert len(debits) == 1
    assert debits[0].tokens_used == 20
    assert debits[0].prompt_tokens == 15
    assert debits[0].completion_tokens == 5
    assert debits[0].agent_run_id is None
    assert debits[0].kind is ComputeDebitKind.PLANNING
    assert debits[0].model == DEFAULT_MODEL
    assert SESSION_NOTES in (debits[0].notes or "")

    zero_calls = {"n": 0}

    def zero_handler(request: httpx.Request) -> httpx.Response:
        zero_calls["n"] += 1
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"total_tokens": 0, "prompt_tokens": 0, "completion_tokens": 0},
            },
        )

    zero_owner = open_session(project_id, session_factory=session_factory)
    zero_app = create_metered_gateway_app(
        zero_owner,
        env={GATEWAY_TOKEN_ENV: "gw-secret"},
        gateway=_gateway(zero_handler),
    )
    zero = await _complete(zero_app)
    assert zero.status_code == 200, zero.text
    assert zero_calls["n"] == 1
    assert len(await _debit_rows(session_factory, project_id)) == 1
    assert await _checkpoint_count(session_factory, project_id) == before


async def test_unfunded_project_is_not_exhausted(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await make_dev_principal(client, display_name="Una", roles=("internal",))
    project_id = await create_owned_project(
        client, actor_id, "session-unfunded", title=TITLE, question=QUESTION
    )
    before = await _checkpoint_count(session_factory, project_id)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json=_OK_BODY)

    owner = open_session(project_id, session_factory=session_factory)
    app = create_metered_gateway_app(
        owner,
        env={GATEWAY_TOKEN_ENV: "gw-secret"},
        gateway=_gateway(handler),
    )
    ok = await _complete(app)
    assert ok.status_code == 200, ok.text
    assert calls["n"] == 1
    assert await _checkpoint_count(session_factory, project_id) == before
    debits = await _debit_rows(session_factory, project_id)
    assert len(debits) == 1
    assert debits[0].tokens_used == 20


async def test_attempted_gateway_turn_debits_and_mints_nothing(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await make_dev_principal(client, display_name="Bea", roles=("internal",))
    project_id = await create_owned_project(client, actor_id, "session-attempted")
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

    owner = HarnessSession(project_id=project_id, session_factory=session_factory)
    app = create_metered_gateway_app(
        owner,
        env={GATEWAY_TOKEN_ENV: "gw-secret"},
        gateway=_gateway(handler),
    )
    failed = await _complete(app)
    assert failed.status_code == 422
    payload = failed.json()
    assert payload["minted"] is False
    assert payload["tokens_used"] == 9
    assert await _checkpoint_count(session_factory, project_id) == before
    debits = await _debit_rows(session_factory, project_id)
    assert len(debits) == 1
    assert debits[0].tokens_used == 9


async def test_live_mcp_after_session_turn_is_the_only_checkpoint_writer(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await make_dev_principal(client, display_name="Ada", roles=("internal",))
    project_id = await create_owned_project(client, actor_id, "session-mcp-door")
    funded = await client.post(
        f"/api/v1/projects/{project_id}/funding",
        json={"amount": "10.00", "currency": "USD", "kind": "top_up", "source": "native"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert funded.status_code == 201, funded.text
    before = await _checkpoint_count(session_factory, project_id)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_OK_BODY)

    owner = open_session(project_id, session_factory=session_factory)
    app = create_metered_gateway_app(
        owner,
        env={GATEWAY_TOKEN_ENV: "gw-secret"},
        gateway=_gateway(handler),
    )
    ok = await _complete(app)
    assert ok.status_code == 200
    assert await _checkpoint_count(session_factory, project_id) == before

    landed = await invoke(
        "run_instrument",
        {
            "project_id": project_id,
            "name": "calc.eval",
            "input": {"expression": "1 + 1"},
        },
        session_factory=session_factory,
        env={"OPENTHEORY_DEV_ACTOR_ID": actor_id},
    )
    assert landed["ok"] is True
    assert landed["minted"] is True
    assert landed["checkpoint_id"]
    assert await _checkpoint_count(session_factory, project_id) == before + 1
