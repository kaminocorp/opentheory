"""DB-backed session-owner metering — the path dsh → gateway actually runs.

Skips without TEST_DATABASE_URL (same gate as the rest of the ledger suite).
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agent.pricing import PriceQuote
from app.harness.campaign import QUESTION, TITLE, create_metered_gateway_app, open_session
from app.harness.gateway import (
    DEFAULT_MODEL,
    GATEWAY_TOKEN_ENV,
    REASON_STREAM,
    REASON_TURN_DEADLINE,
    GatewayClient,
    GatewayResponse,
)
from app.harness.live_mcp import invoke
from app.harness.session import (
    HOLD_NOTES,
    REASON_DAILY_CAP,
    REASON_PROJECT_BUDGET,
    REASON_TURN_ROOM,
    SESSION_NOTES,
    TURN_TIMEOUT_ENV,
    HarnessSession,
    TurnRefused,
    harness_tokens_used_today,
    hold_notes,
    is_daily_cap_adjustment,
    parse_hold_id,
    release_notes,
)
from app.models.actor import Actor
from app.models.checkpoint import Checkpoint
from app.models.compute_debit import ComputeDebit
from app.models.enums import ComputeDebitKind, ComputeDebitRateSource
from app.models.funding import FundingAllocation
from app.services.compute import BUDGET_EXHAUSTED
from app.services.harness_meter import load_today_adjustments
from tests.principals import create_owned_project, make_dev_principal


def _actor_env(actor_id: str) -> dict[str, str]:
    return {"OPENTHEORY_DEV_ACTOR_ID": actor_id}


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


async def _complete(
    app,
    *,
    token: str = "gw-secret",
    model: str | None = DEFAULT_MODEL,
    max_tokens: int | object = ...,
    extra: dict | None = None,
) -> httpx.Response:
    body: dict = {
        "messages": [{"role": "user", "content": "hi"}],
        "models": ["openai/gpt-4o"],
        "route": "fallback",
    }
    if model is not None:
        body["model"] = model
    if max_tokens is not ...:
        body["max_tokens"] = max_tokens
    if extra:
        body.update(extra)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://gw") as client:
        return await client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {token}"},
            json=body,
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

    owner = open_session(
        project_id,
        session_factory=session_factory,
        actor_env=_actor_env(actor_id),
    )
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
        actor_env=_actor_env(actor_id),
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

    owner = open_session(
        project_id,
        session_factory=session_factory,
        actor_env=_actor_env(actor_id),
    )
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
    assert not hasattr(ComputeDebit, "actor_id")

    async with session_factory() as session:
        actor = await session.get(Actor, UUID(actor_id))
        assert actor is not None
        allocations = (
            await session.execute(
                select(FundingAllocation).where(
                    FundingAllocation.project_id == UUID(project_id)
                )
            )
        ).scalars().all()
        assert len(allocations) == 1
        assert allocations[0].account_id == actor.account_id
        assert allocations[0].amount == Decimal("10.00")

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

    zero_owner = open_session(
        project_id,
        session_factory=session_factory,
        actor_env=_actor_env(actor_id),
    )
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

    owner = open_session(
        project_id,
        session_factory=session_factory,
        actor_env=_actor_env(actor_id),
    )
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

    owner = HarnessSession(
        project_id=project_id,
        session_factory=session_factory,
        actor_env=_actor_env(actor_id),
    )
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

    owner = open_session(
        project_id,
        session_factory=session_factory,
        actor_env=_actor_env(actor_id),
    )
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
        actor_env=_actor_env(actor_id),
        env={"OPENTHEORY_DEV_ACTOR_ID": actor_id},
    )
    assert landed["ok"] is True
    assert landed["minted"] is True
    assert landed["checkpoint_id"]
    assert await _checkpoint_count(session_factory, project_id) == before + 1


async def _add_harness_debit(
    session_factory: async_sessionmaker,
    project_id: str,
    *,
    tokens_used: int,
    notes: str | None = SESSION_NOTES,
    created_at: datetime | None = None,
) -> None:
    async with session_factory() as session:
        row = ComputeDebit(
            project_id=UUID(project_id),
            tokens_used=tokens_used,
            amount=Decimal("0.01"),
            currency="USD",
            rate_per_1k=Decimal("0.50"),
            rate_source=ComputeDebitRateSource.BLENDED_FALLBACK,
            kind=ComputeDebitKind.PLANNING,
            notes=notes,
        )
        if created_at is not None:
            row.created_at = created_at
            row.updated_at = created_at
        session.add(row)
        await session.commit()


async def _add_daily_cap_hold(
    session_factory: async_sessionmaker,
    project_id: str,
    *,
    tokens_used: int,
    hold_id: UUID | None = None,
    created_at: datetime | None = None,
) -> UUID | None:
    """Append-only leftover hold. Amount 0 — not a pot debit."""
    notes = HOLD_NOTES if hold_id is None else hold_notes(hold_id)
    async with session_factory() as session:
        row = ComputeDebit(
            project_id=UUID(project_id),
            tokens_used=tokens_used,
            amount=Decimal("0"),
            currency="USD",
            rate_per_1k=Decimal("0"),
            rate_source=ComputeDebitRateSource.BLENDED_FALLBACK,
            kind=ComputeDebitKind.PLANNING,
            notes=notes,
        )
        if created_at is not None:
            row.created_at = created_at
            row.updated_at = created_at
        session.add(row)
        await session.commit()
    return hold_id


async def _adjustment_notes(
    session_factory: async_sessionmaker, project_id: str
) -> list[str]:
    async with session_factory() as session:
        result = await session.execute(
            select(ComputeDebit).where(ComputeDebit.project_id == UUID(project_id))
        )
        return [
            row.notes or ""
            for row in result.scalars().all()
            if is_daily_cap_adjustment(row.notes)
        ]


async def test_daily_token_cap_refuses_before_model_and_survives_restart(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await make_dev_principal(client, display_name="Cap", roles=("internal",))
    project_id = await create_owned_project(
        client, actor_id, "session-daily-cap", title=TITLE, question=QUESTION
    )
    funded = await client.post(
        f"/api/v1/projects/{project_id}/funding",
        json={"amount": "10.00", "currency": "USD", "kind": "top_up", "source": "native"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert funded.status_code == 201, funded.text
    before = await _checkpoint_count(session_factory, project_id)

    first = open_session(
        project_id, daily_token_cap=20, session_factory=session_factory,
        actor_env=_actor_env(actor_id),
    )
    first_app = create_metered_gateway_app(
        first,
        env={GATEWAY_TOKEN_ENV: "gw-secret"},
        gateway=_gateway(lambda _request: httpx.Response(200, json=_OK_BODY)),
    )
    ok = await _complete(first_app)
    assert ok.status_code == 200, ok.text
    assert len(await _debit_rows(session_factory, project_id)) == 1

    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        calls["n"] += 1
        raise AssertionError("daily cap must refuse before the LLM call")

    # New process: turn_index resets to 0. Today's ledger sum does not.
    restarted = HarnessSession(
        project_id=project_id,
        turn_index=0,
        daily_token_cap=20,
        session_factory=session_factory,
        actor_env=_actor_env(actor_id),
    )
    assert restarted.turn_index == 0
    app = create_metered_gateway_app(
        restarted,
        env={GATEWAY_TOKEN_ENV: "gw-secret"},
        gateway=_gateway(handler),
    )
    refused = await _complete(app)
    assert refused.status_code == 422
    payload = refused.json()
    assert payload["refused"] is True
    assert payload["error"] == REASON_DAILY_CAP
    assert payload["tokens_used"] == 0
    assert payload["minted"] is False
    assert calls["n"] == 0
    assert await _checkpoint_count(session_factory, project_id) == before
    assert len(await _debit_rows(session_factory, project_id)) == 1


async def test_yesterday_harness_spend_does_not_hit_today_cap(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await make_dev_principal(client, display_name="Yda", roles=("internal",))
    project_id = await create_owned_project(client, actor_id, "session-daily-yesterday")
    funded = await client.post(
        f"/api/v1/projects/{project_id}/funding",
        json={"amount": "10.00", "currency": "USD", "kind": "top_up", "source": "native"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert funded.status_code == 201, funded.text
    await _add_harness_debit(
        session_factory,
        project_id,
        tokens_used=500,
        notes=f"{SESSION_NOTES}; rate fallback: blended_fallback",
        created_at=datetime.now(UTC) - timedelta(days=1),
    )
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json=_OK_BODY)

    owner = open_session(
        project_id, daily_token_cap=20, session_factory=session_factory,
        actor_env=_actor_env(actor_id),
    )
    app = create_metered_gateway_app(
        owner,
        env={GATEWAY_TOKEN_ENV: "gw-secret"},
        gateway=_gateway(handler),
    )
    ok = await _complete(app)
    assert ok.status_code == 200, ok.text
    assert calls["n"] == 1
    assert len(await _debit_rows(session_factory, project_id)) == 2


async def test_non_harness_debits_do_not_count_toward_daily_cap(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await make_dev_principal(client, display_name="Iso", roles=("internal",))
    project_id = await create_owned_project(client, actor_id, "session-daily-isolate")
    funded = await client.post(
        f"/api/v1/projects/{project_id}/funding",
        json={"amount": "10.00", "currency": "USD", "kind": "top_up", "source": "native"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert funded.status_code == 201, funded.text
    await _add_harness_debit(
        session_factory, project_id, tokens_used=10_000, notes=None
    )
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json=_OK_BODY)

    owner = open_session(
        project_id, daily_token_cap=20, session_factory=session_factory,
        actor_env=_actor_env(actor_id),
    )
    app = create_metered_gateway_app(
        owner,
        env={GATEWAY_TOKEN_ENV: "gw-secret"},
        gateway=_gateway(handler),
    )
    ok = await _complete(app)
    assert ok.status_code == 200, ok.text
    assert calls["n"] == 1


async def test_daily_cap_notes_prefix_is_literal(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    """Underscores in harness_session_turn are not LIKE wildcards.

    ``harness-session-turn extra`` would match an unescaped
    ``notes LIKE 'harness_session_turn%'``. It must not count. A sibling
    whose notes really start with the marker — including the
    rate-fallback suffix ``record_compute_debit`` appends — must count.
    """
    actor_id = await make_dev_principal(client, display_name="Like", roles=("internal",))
    project_id = await create_owned_project(client, actor_id, "session-daily-like")
    lookalike = "harness-session-turn extra"
    assert "_" not in lookalike
    await _add_harness_debit(
        session_factory, project_id, tokens_used=10_000, notes=lookalike
    )
    async with session_factory() as session:
        assert await harness_tokens_used_today(session, UUID(project_id)) == 0

    await _add_harness_debit(
        session_factory,
        project_id,
        tokens_used=7,
        notes=f"{SESSION_NOTES}; rate fallback: blended_fallback",
    )
    async with session_factory() as session:
        assert await harness_tokens_used_today(session, UUID(project_id)) == 7


async def test_unfunded_project_still_hits_daily_cap(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await make_dev_principal(client, display_name="Una", roles=("internal",))
    project_id = await create_owned_project(client, actor_id, "session-daily-unfunded")
    before = await _checkpoint_count(session_factory, project_id)
    await _add_harness_debit(session_factory, project_id, tokens_used=20)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        calls["n"] += 1
        raise AssertionError("daily cap must refuse before the LLM call")

    owner = HarnessSession(
        project_id=project_id,
        turn_index=0,
        daily_token_cap=20,
        session_factory=session_factory,
        actor_env=_actor_env(actor_id),
    )
    app = create_metered_gateway_app(
        owner,
        env={GATEWAY_TOKEN_ENV: "gw-secret"},
        gateway=_gateway(handler),
    )
    refused = await _complete(app)
    assert refused.status_code == 422
    assert refused.json()["error"] == REASON_DAILY_CAP
    assert refused.json()["minted"] is False
    assert calls["n"] == 0
    assert await _checkpoint_count(session_factory, project_id) == before
    assert len(await _debit_rows(session_factory, project_id)) == 1


async def test_overlapping_authorizations_cannot_both_spend_past_cap(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    """Two in-flight turns cannot both pass authorize() and both debit past the cap.

    The first remaining-room hold is visible to the second authorize under
    the project-row lock. The second refuses (no OpenRouter call). After
    convert, today's harness sum is one turn, not two.
    """
    actor_id = await make_dev_principal(client, display_name="Race", roles=("internal",))
    project_id = await create_owned_project(client, actor_id, "session-daily-race")
    before = await _checkpoint_count(session_factory, project_id)

    first = HarnessSession(
        project_id=project_id,
        daily_token_cap=20,
        session_factory=session_factory,
        actor_env=_actor_env(actor_id),
    )
    second = HarnessSession(
        project_id=project_id,
        daily_token_cap=20,
        session_factory=session_factory,
        actor_env=_actor_env(actor_id),
    )

    async def _authorize(owner: HarnessSession):
        try:
            return ("ok", owner, await owner.authorize())
        except TurnRefused as exc:
            return ("refused", owner, exc)

    outcomes = await asyncio.gather(_authorize(first), _authorize(second))
    winners = [item for item in outcomes if item[0] == "ok"]
    losers = [item for item in outcomes if item[0] == "refused"]
    assert len(winners) == 1
    assert len(losers) == 1
    assert losers[0][2].reason == REASON_DAILY_CAP

    _, winner, hold = winners[0]
    spent = await winner.record_spend(
        tokens_used=20,
        model=DEFAULT_MODEL,
        prompt_tokens=15,
        completion_tokens=5,
        hold=hold,
    )
    assert spent is True
    async with session_factory() as session:
        assert await harness_tokens_used_today(session, UUID(project_id)) == 20
    assert len(await _debit_rows(session_factory, project_id)) == 1
    assert await _checkpoint_count(session_factory, project_id) == before

    class PauseGateway:
        def __init__(self) -> None:
            self.entered = asyncio.Event()
            self.release = asyncio.Event()
            self.calls = 0

        async def complete(self, **_kwargs: object) -> GatewayResponse:
            self.calls += 1
            self.entered.set()
            await self.release.wait()
            return GatewayResponse(
                text="ok",
                tokens_used=20,
                model=DEFAULT_MODEL,
                prompt_tokens=15,
                completion_tokens=5,
            )

    # Fresh project: overlapping HTTP completions on the session-owned path.
    http_project = await create_owned_project(client, actor_id, "session-daily-race-http")
    pause = PauseGateway()
    owner = open_session(
        http_project, daily_token_cap=20, session_factory=session_factory,
        actor_env=_actor_env(actor_id),
    )
    app = create_metered_gateway_app(
        owner,
        env={GATEWAY_TOKEN_ENV: "gw-secret"},
        gateway=pause,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://gw") as http:
        async def _post() -> httpx.Response:
            return await http.post(
                "/v1/chat/completions",
                headers={"Authorization": "Bearer gw-secret"},
                json={
                    "model": DEFAULT_MODEL,
                    "messages": [{"role": "user", "content": "hi"}],
                },
            )

        inflight = asyncio.create_task(_post())
        await asyncio.wait_for(pause.entered.wait(), timeout=5)
        overlapping = await asyncio.wait_for(_post(), timeout=5)
        assert overlapping.status_code == 422
        payload = overlapping.json()
        assert payload["refused"] is True
        assert payload["error"] == REASON_DAILY_CAP
        assert payload["tokens_used"] == 0
        assert payload["minted"] is False
        assert pause.calls == 1
        pause.release.set()
        completed = await inflight
    assert completed.status_code == 200, completed.text
    assert pause.calls == 1
    assert len(await _debit_rows(session_factory, http_project)) == 1
    async with session_factory() as session:
        assert await harness_tokens_used_today(session, UUID(http_project)) == 20
    assert await _checkpoint_count(session_factory, http_project) == 0


async def test_orphaned_hold_is_released_after_ttl_without_reopening_race(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    """A crash leftover hold must not pin the UTC day; live overlap still refuses.

    Fresh authorize-without-convert still refuses a second authorize (the
    0.47.0 race close). A hold older than the TTL is released on the next
    authorize (append-only credit). Two overlapping authorizes after that
    recovery still cannot both debit past the cap.
    """
    actor_id = await make_dev_principal(client, display_name="Orphan", roles=("internal",))
    fresh_project = await create_owned_project(client, actor_id, "session-daily-orphan-fresh")
    first = HarnessSession(
        project_id=fresh_project,
        daily_token_cap=20,
        session_factory=session_factory,
        actor_env=_actor_env(actor_id),
    )
    second = HarnessSession(
        project_id=fresh_project,
        daily_token_cap=20,
        session_factory=session_factory,
        actor_env=_actor_env(actor_id),
    )
    fresh_hold = await first.authorize()
    assert fresh_hold is not None
    assert parse_hold_id(hold_notes(fresh_hold.hold_id)) == fresh_hold.hold_id
    try:
        await second.authorize()
        raise AssertionError("fresh unmatched hold must still refuse a second authorize")
    except TurnRefused as exc:
        assert exc.reason == REASON_DAILY_CAP
    async with session_factory() as session:
        assert await harness_tokens_used_today(session, UUID(fresh_project)) == 20

    stale_project = await create_owned_project(client, actor_id, "session-daily-orphan-stale")
    stale_id = uuid4()
    await _add_daily_cap_hold(
        session_factory,
        stale_project,
        tokens_used=20,
        hold_id=stale_id,
        created_at=datetime.now(UTC) - timedelta(seconds=301),
    )
    recovered = HarnessSession(
        project_id=stale_project,
        daily_token_cap=20,
        session_factory=session_factory,
        actor_env=_actor_env(actor_id),
    )
    recovered_hold = await recovered.authorize()
    assert recovered_hold is not None
    notes = await _adjustment_notes(session_factory, stale_project)
    assert any(row == release_notes(stale_id) for row in notes)
    assert any(parse_hold_id(row) == recovered_hold.hold_id for row in notes)
    spent = await recovered.record_spend(
        tokens_used=7,
        model=DEFAULT_MODEL,
        prompt_tokens=5,
        completion_tokens=2,
        hold=recovered_hold,
    )
    assert spent is True
    async with session_factory() as session:
        assert await harness_tokens_used_today(session, UUID(stale_project)) == 7
    assert len(await _debit_rows(session_factory, stale_project)) == 1

    race_project = await create_owned_project(client, actor_id, "session-daily-orphan-race")
    await _add_daily_cap_hold(
        session_factory,
        race_project,
        tokens_used=20,
        hold_id=uuid4(),
        created_at=datetime.now(UTC) - timedelta(seconds=301),
    )
    # Pre-0.48.0 leftover (no hold_id) must also recover.
    legacy_project = await create_owned_project(client, actor_id, "session-daily-orphan-legacy")
    await _add_daily_cap_hold(
        session_factory,
        legacy_project,
        tokens_used=20,
        created_at=datetime.now(UTC) - timedelta(seconds=301),
    )
    legacy = HarnessSession(
        project_id=legacy_project,
        daily_token_cap=20,
        session_factory=session_factory,
        actor_env=_actor_env(actor_id),
    )
    legacy_hold = await legacy.authorize()
    assert legacy_hold is not None
    await legacy.record_spend(
        tokens_used=4,
        model=DEFAULT_MODEL,
        hold=legacy_hold,
    )
    async with session_factory() as session:
        assert await harness_tokens_used_today(session, UUID(legacy_project)) == 4

    left = HarnessSession(
        project_id=race_project,
        daily_token_cap=20,
        session_factory=session_factory,
        actor_env=_actor_env(actor_id),
    )
    right = HarnessSession(
        project_id=race_project,
        daily_token_cap=20,
        session_factory=session_factory,
        actor_env=_actor_env(actor_id),
    )

    async def _authorize(owner: HarnessSession):
        try:
            return ("ok", owner, await owner.authorize())
        except TurnRefused as exc:
            return ("refused", owner, exc)

    outcomes = await asyncio.gather(_authorize(left), _authorize(right))
    winners = [item for item in outcomes if item[0] == "ok"]
    losers = [item for item in outcomes if item[0] == "refused"]
    assert len(winners) == 1
    assert len(losers) == 1
    assert losers[0][2].reason == REASON_DAILY_CAP
    _, winner, hold = winners[0]
    spent = await winner.record_spend(
        tokens_used=20,
        model=DEFAULT_MODEL,
        prompt_tokens=15,
        completion_tokens=5,
        hold=hold,
    )
    assert spent is True
    async with session_factory() as session:
        assert await harness_tokens_used_today(session, UUID(race_project)) == 20
    assert len(await _debit_rows(session_factory, race_project)) == 1
    assert await _checkpoint_count(session_factory, race_project) == 0


def _live_quote(rate: Decimal = Decimal("1.00")) -> PriceQuote:
    return PriceQuote(
        source=ComputeDebitRateSource.OPENROUTER_LIVE,
        effective_rate_per_1k=rate,
        prompt_rate_per_1k=rate,
        completion_rate_per_1k=rate,
        model=DEFAULT_MODEL,
    )


def _fallback_quote(rate: Decimal = Decimal("1.00")) -> PriceQuote:
    return PriceQuote(
        source=ComputeDebitRateSource.BLENDED_FALLBACK,
        effective_rate_per_1k=rate,
        fallback_reason="live_prices_disabled",
        model=DEFAULT_MODEL,
    )


async def test_clamp_is_min_of_daily_and_pot_when_price_known(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await make_dev_principal(client, display_name="Clamp", roles=("internal",))
    project_id = await create_owned_project(client, actor_id, "session-clamp-known")
    funded = await client.post(
        f"/api/v1/projects/{project_id}/funding",
        json={"amount": "0.05", "currency": "USD", "kind": "top_up", "source": "native"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert funded.status_code == 201, funded.text

    owner = HarnessSession(
        project_id=project_id,
        daily_token_cap=20_000,
        session_factory=session_factory,
        actor_env=_actor_env(actor_id),
    )
    hold = await owner.authorize(model=DEFAULT_MODEL, quote=_live_quote())
    assert hold is not None
    assert hold.daily_room == 20_000
    assert hold.pot_room == 50
    assert hold.clamp == 50
    assert hold.price_known is True
    assert hold.tokens == 20_000
    notes = await _adjustment_notes(session_factory, project_id)
    assert any(HOLD_NOTES in row for row in notes)
    await owner.release_hold(hold)

    tight = await create_owned_project(client, actor_id, "session-clamp-daily-tighter")
    funded_tight = await client.post(
        f"/api/v1/projects/{tight}/funding",
        json={"amount": "10.00", "currency": "USD", "kind": "top_up", "source": "native"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert funded_tight.status_code == 201, funded_tight.text
    await _add_harness_debit(session_factory, tight, tokens_used=10)
    tight_owner = HarnessSession(
        project_id=tight,
        daily_token_cap=50,
        session_factory=session_factory,
        actor_env=_actor_env(actor_id),
    )
    tight_hold = await tight_owner.authorize(model=DEFAULT_MODEL, quote=_live_quote())
    assert tight_hold is not None
    assert tight_hold.daily_room == 40
    assert tight_hold.pot_room is not None
    assert tight_hold.pot_room > 40
    assert tight_hold.clamp == 40
    await tight_owner.release_hold(tight_hold)


async def test_clamp_is_daily_room_when_price_unknown(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await make_dev_principal(client, display_name="Unk", roles=("internal",))
    project_id = await create_owned_project(client, actor_id, "session-clamp-unknown")
    funded = await client.post(
        f"/api/v1/projects/{project_id}/funding",
        json={"amount": "0.05", "currency": "USD", "kind": "top_up", "source": "native"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert funded.status_code == 201, funded.text

    owner = HarnessSession(
        project_id=project_id,
        daily_token_cap=80,
        session_factory=session_factory,
        actor_env=_actor_env(actor_id),
    )
    hold = await owner.authorize(model=DEFAULT_MODEL, quote=_fallback_quote())
    assert hold is not None
    assert hold.price_known is False
    assert hold.pot_room is None
    assert hold.daily_room == 80
    assert hold.clamp == 80
    assert hold.tokens == 80
    notes = await _adjustment_notes(session_factory, project_id)
    assert all("pot_hold=" not in row for row in notes)
    await owner.release_hold(hold)

    no_quote = await owner.authorize()
    assert no_quote is not None
    assert no_quote.price_known is False
    assert no_quote.clamp == 80
    await owner.release_hold(no_quote)


async def test_gateway_clamps_max_tokens_to_pot_room_when_price_known(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor_id = await make_dev_principal(client, display_name="Pot", roles=("internal",))
    project_id = await create_owned_project(client, actor_id, "session-clamp-http-pot")
    funded = await client.post(
        f"/api/v1/projects/{project_id}/funding",
        json={"amount": "0.05", "currency": "USD", "kind": "top_up", "source": "native"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert funded.status_code == 201, funded.text

    async def _quote(model: str | None, **_kwargs: object) -> PriceQuote:
        return _live_quote()

    monkeypatch.setattr("app.harness.session.quote_model_price", _quote)
    seen: dict[str, int | None] = {"max_tokens": None}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen["max_tokens"] = body.get("max_tokens")
        return httpx.Response(200, json=_OK_BODY)

    owner = open_session(
        project_id, daily_token_cap=20_000, session_factory=session_factory,
        actor_env=_actor_env(actor_id),
    )
    app = create_metered_gateway_app(
        owner,
        env={GATEWAY_TOKEN_ENV: "gw-secret"},
        gateway=_gateway(handler),
    )
    ok = await _complete(app)
    assert ok.status_code == 200, ok.text
    assert seen["max_tokens"] == 50
    assert ok.json()["clamp"] == 50
    assert ok.json()["overshoot"] == 0
    assert ok.json()["price_known"] is True
    assert ok.json()["pot_room"] == 50
    assert ok.json()["usage"]["total_tokens"] == 20
    debits = await _debit_rows(session_factory, project_id)
    assert len(debits) == 1
    assert debits[0].tokens_used == 20
    notes = debits[0].notes or ""
    assert "clamp=50" in notes
    assert "pot_room=50" in notes
    assert "overshoot=" not in notes


async def test_below_floor_refuses_without_provider_or_debit(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await make_dev_principal(client, display_name="Floor", roles=("internal",))
    project_id = await create_owned_project(client, actor_id, "session-clamp-floor")
    before = await _checkpoint_count(session_factory, project_id)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        calls["n"] += 1
        raise AssertionError("room below floor must refuse before the LLM call")

    owner = HarnessSession(
        project_id=project_id,
        daily_token_cap=20,
        turn_token_floor=100,
        session_factory=session_factory,
        actor_env=_actor_env(actor_id),
    )
    app = create_metered_gateway_app(
        owner,
        env={GATEWAY_TOKEN_ENV: "gw-secret"},
        gateway=_gateway(handler),
    )
    refused = await _complete(app)
    assert refused.status_code == 422
    payload = refused.json()
    assert payload["refused"] is True
    assert payload["error"] == REASON_TURN_ROOM
    assert payload["tokens_used"] == 0
    assert payload["minted"] is False
    assert calls["n"] == 0
    assert await _checkpoint_count(session_factory, project_id) == before
    assert len(await _debit_rows(session_factory, project_id)) == 0
    async with session_factory() as session:
        assert await harness_tokens_used_today(session, UUID(project_id)) == 0


async def test_provider_overshoot_is_recorded_truthfully(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await make_dev_principal(client, display_name="Over", roles=("internal",))
    project_id = await create_owned_project(client, actor_id, "session-clamp-overshoot")
    seen: dict[str, int | None] = {"max_tokens": None}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen["max_tokens"] = body.get("max_tokens")
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "too much"}}],
                "usage": {"total_tokens": 80, "prompt_tokens": 30, "completion_tokens": 50},
            },
        )

    owner = HarnessSession(
        project_id=project_id,
        daily_token_cap=50,
        session_factory=session_factory,
        actor_env=_actor_env(actor_id),
    )
    app = create_metered_gateway_app(
        owner,
        env={GATEWAY_TOKEN_ENV: "gw-secret"},
        gateway=_gateway(handler),
    )
    ok = await _complete(app)
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert seen["max_tokens"] == 50
    assert body["usage"]["total_tokens"] == 80
    assert body["clamp"] == 50
    assert body["overshoot"] == 30
    assert body["price_known"] is False
    debits = await _debit_rows(session_factory, project_id)
    assert len(debits) == 1
    assert debits[0].tokens_used == 80
    notes = debits[0].notes or ""
    assert "overshoot=30" in notes
    assert "clamp=50" in notes
    assert "price_unknown" in notes
    assert notes.startswith(SESSION_NOTES)
    assert "pot_room=none" in notes
    async with session_factory() as session:
        assert await harness_tokens_used_today(session, UUID(project_id)) == 80


async def test_unfunded_known_price_clamps_to_daily_room(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor_id = await make_dev_principal(client, display_name="Unfunded", roles=("internal",))
    project_id = await create_owned_project(client, actor_id, "session-clamp-unfunded")

    async def _quote(model: str | None, **_kwargs: object) -> PriceQuote:
        return _live_quote()

    monkeypatch.setattr("app.harness.session.quote_model_price", _quote)
    seen: dict[str, int | None] = {"max_tokens": None}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen["max_tokens"] = body.get("max_tokens")
        return httpx.Response(200, json=_OK_BODY)

    owner = open_session(
        project_id,
        daily_token_cap=80,
        session_factory=session_factory,
        actor_env=_actor_env(actor_id),
    )
    hold = await owner.authorize(model=DEFAULT_MODEL, quote=_live_quote())
    assert hold is not None
    assert hold.price_known is True
    assert hold.pot_room is None
    assert hold.daily_room == 80
    assert hold.clamp == 80
    assert hold.tokens == 80
    notes = await _adjustment_notes(session_factory, project_id)
    assert all("pot_hold=" not in row for row in notes)
    await owner.release_hold(hold)

    app = create_metered_gateway_app(
        open_session(
            project_id,
            daily_token_cap=80,
            session_factory=session_factory,
            actor_env=_actor_env(actor_id),
        ),
        env={GATEWAY_TOKEN_ENV: "gw-secret"},
        gateway=_gateway(handler),
    )
    ok = await _complete(app)
    assert ok.status_code == 200, ok.text
    payload = ok.json()
    assert "refused" not in payload
    assert seen["max_tokens"] == 80
    assert payload["clamp"] == 80
    assert payload["price_known"] is True
    assert payload["pot_room"] is None
    debits = await _debit_rows(session_factory, project_id)
    assert len(debits) == 1
    notes = debits[0].notes or ""
    assert "pot_room=none" in notes
    assert "clamp=80" in notes
    ops = await client.get(f"/api/v1/projects/{project_id}/ops")
    assert ops.status_code == 200, ops.text
    last = ops.json()["last_turn"]
    assert last is not None
    assert last["pot_room"] is None
    assert last["price_known"] is True
    assert last["clamp"] == 80
    assert "pot room was not applied" in last["note"]
    assert "min of daily room and pot room" not in last["note"]


async def test_pot_clamp_uses_completion_rate_not_live_mean(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await make_dev_principal(client, display_name="Split", roles=("internal",))
    project_id = await create_owned_project(client, actor_id, "session-clamp-completion-rate")
    funded = await client.post(
        f"/api/v1/projects/{project_id}/funding",
        json={"amount": "0.08", "currency": "USD", "kind": "top_up", "source": "native"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert funded.status_code == 201, funded.text

    quote = PriceQuote(
        source=ComputeDebitRateSource.OPENROUTER_LIVE,
        effective_rate_per_1k=Decimal("2.50"),
        prompt_rate_per_1k=Decimal("1.00"),
        completion_rate_per_1k=Decimal("4.00"),
        model=DEFAULT_MODEL,
    )
    owner = HarnessSession(
        project_id=project_id,
        daily_token_cap=20_000,
        session_factory=session_factory,
        actor_env=_actor_env(actor_id),
    )
    hold = await owner.authorize(model=DEFAULT_MODEL, quote=quote)
    assert hold is not None
    assert hold.price_known is True
    # Mean $2.50 / 1k would buy 32 tokens; completion $4 / 1k buys 20.
    assert hold.pot_room == 20
    assert hold.clamp == 20
    assert hold.tokens == 20_000
    await owner.release_hold(hold)


async def test_http_keeps_caller_smaller_max_tokens(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor_id = await make_dev_principal(client, display_name="Small", roles=("internal",))
    project_id = await create_owned_project(client, actor_id, "session-clamp-caller-max")
    funded = await client.post(
        f"/api/v1/projects/{project_id}/funding",
        json={"amount": "0.05", "currency": "USD", "kind": "top_up", "source": "native"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert funded.status_code == 201, funded.text

    async def _quote(model: str | None, **_kwargs: object) -> PriceQuote:
        return _live_quote()

    monkeypatch.setattr("app.harness.session.quote_model_price", _quote)
    seen: dict[str, int | None] = {"max_tokens": None}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen["max_tokens"] = body.get("max_tokens")
        return httpx.Response(200, json=_OK_BODY)

    owner = open_session(
        project_id, daily_token_cap=20_000, session_factory=session_factory,
        actor_env=_actor_env(actor_id),
    )
    app = create_metered_gateway_app(
        owner,
        env={GATEWAY_TOKEN_ENV: "gw-secret"},
        gateway=_gateway(handler),
    )
    ok = await _complete(app, max_tokens=20)
    assert ok.status_code == 200, ok.text
    assert seen["max_tokens"] == 20
    assert ok.json()["clamp"] == 50


async def test_http_omitted_model_authorizes_resolved_default(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor_id = await make_dev_principal(client, display_name="Model", roles=("internal",))
    project_id = await create_owned_project(client, actor_id, "session-clamp-omit-model")
    quoted: list[str | None] = []

    async def _quote(model: str | None, **_kwargs: object) -> PriceQuote:
        quoted.append(model)
        return _live_quote()

    monkeypatch.setattr("app.harness.session.quote_model_price", _quote)
    seen: dict[str, str | None] = {"model": None}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen["model"] = body.get("model")
        return httpx.Response(200, json=_OK_BODY)

    owner = open_session(
        project_id, daily_token_cap=20_000, session_factory=session_factory,
        actor_env=_actor_env(actor_id),
    )
    app = create_metered_gateway_app(
        owner,
        env={GATEWAY_TOKEN_ENV: "gw-secret"},
        gateway=_gateway(handler),
    )
    ok = await _complete(app, model=None)
    assert ok.status_code == 200, ok.text
    assert quoted == [DEFAULT_MODEL]
    assert seen["model"] == DEFAULT_MODEL
    assert ok.json()["model"] == DEFAULT_MODEL


async def test_http_invalid_max_tokens_is_422(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await make_dev_principal(client, display_name="BadMax", roles=("internal",))
    project_id = await create_owned_project(client, actor_id, "session-clamp-bad-max")
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        calls["n"] += 1
        raise AssertionError("invalid max_tokens must not reach OpenRouter")

    owner = open_session(
        project_id,
        daily_token_cap=80,
        session_factory=session_factory,
        actor_env=_actor_env(actor_id),
    )
    app = create_metered_gateway_app(
        owner,
        env={GATEWAY_TOKEN_ENV: "gw-secret"},
        gateway=_gateway(handler),
    )
    for bad in (0, -3, "nope"):
        refused = await _complete(app, max_tokens=bad)
        assert refused.status_code == 422, refused.text
        payload = refused.json()
        assert payload["tokens_used"] == 0
        assert "positive integer" in payload["error"]
        assert payload.get("refused") is not True
    assert calls["n"] == 0
    assert len(await _debit_rows(session_factory, project_id)) == 0
    async with session_factory() as session:
        assert await harness_tokens_used_today(session, UUID(project_id)) == 0


async def _hold_rows(
    session_factory: async_sessionmaker, project_id: str
) -> list[ComputeDebit]:
    async with session_factory() as session:
        return await load_today_adjustments(session, UUID(project_id))


async def test_overlapping_authorize_on_tight_pot_is_refused_for_daily_cap(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    """0.50 already serializes: the hold occupies remaining daily room.

    A second overlapping authorize — known-price, price-unknown, or after
    a mid-flight pot top-up — is refused for the daily-cap hold reason.
    No provider call, no debit, no extra hold.
    """
    actor_id = await make_dev_principal(client, display_name="TightPot", roles=("internal",))
    project_id = await create_owned_project(client, actor_id, "session-tight-pot-serialize")
    funded = await client.post(
        f"/api/v1/projects/{project_id}/funding",
        json={"amount": "0.05", "currency": "USD", "kind": "top_up", "source": "native"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert funded.status_code == 201, funded.text
    before = await _checkpoint_count(session_factory, project_id)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        calls["n"] += 1
        raise AssertionError("overlapping authorize must refuse before the LLM call")

    first = HarnessSession(
        project_id=project_id,
        daily_token_cap=20_000,
        session_factory=session_factory,
        actor_env=_actor_env(actor_id),
    )
    hold = await first.authorize(model=DEFAULT_MODEL, quote=_live_quote())
    assert hold is not None
    assert hold.tokens == 20_000
    assert hold.daily_room == 20_000
    assert hold.clamp == 50
    assert hold.pot_room == 50
    assert hold.price_known is True
    holds_after_first = await _hold_rows(session_factory, project_id)
    assert len(holds_after_first) == 1
    assert holds_after_first[0].tokens_used == 20_000

    second = HarnessSession(
        project_id=project_id,
        daily_token_cap=20_000,
        session_factory=session_factory,
        actor_env=_actor_env(actor_id),
    )
    try:
        await second.authorize(model=DEFAULT_MODEL, quote=_live_quote())
        raise AssertionError("known-price overlapping authorize must refuse")
    except TurnRefused as exc:
        assert exc.reason == REASON_DAILY_CAP

    try:
        await second.authorize(model=DEFAULT_MODEL, quote=_fallback_quote())
        raise AssertionError("price-unknown overlapping authorize must refuse")
    except TurnRefused as exc:
        assert exc.reason == REASON_DAILY_CAP

    topped = await client.post(
        f"/api/v1/projects/{project_id}/funding",
        json={"amount": "1.00", "currency": "USD", "kind": "top_up", "source": "native"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert topped.status_code == 201, topped.text
    try:
        await second.authorize(model=DEFAULT_MODEL, quote=_live_quote())
        raise AssertionError("mid-flight top-up must not admit a second turn")
    except TurnRefused as exc:
        assert exc.reason == REASON_DAILY_CAP

    app = create_metered_gateway_app(
        second,
        env={GATEWAY_TOKEN_ENV: "gw-secret"},
        gateway=_gateway(handler),
    )
    refused = await _complete(app)
    assert refused.status_code == 422
    payload = refused.json()
    assert payload["refused"] is True
    assert payload["error"] == REASON_DAILY_CAP
    assert payload["tokens_used"] == 0
    assert payload["minted"] is False
    assert calls["n"] == 0
    assert len(await _debit_rows(session_factory, project_id)) == 0
    assert len(await _hold_rows(session_factory, project_id)) == 1
    assert await _checkpoint_count(session_factory, project_id) == before
    async with session_factory() as session:
        assert await harness_tokens_used_today(session, UUID(project_id)) == 20_000
    await first.release_hold(hold)


class _TrickleStream(httpx.AsyncByteStream):
    def __init__(self, chunks: list[bytes], delay_s: float) -> None:
        self._chunks = chunks
        self._delay_s = delay_s

    async def __aiter__(self):
        for index, chunk in enumerate(self._chunks):
            if index:
                await asyncio.sleep(self._delay_s)
            yield chunk


class _TrickleTransport(httpx.AsyncBaseTransport):
    def __init__(self, delay_s: float = 0.4) -> None:
        self.calls = 0
        self._delay_s = delay_s

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        body = json.dumps(_OK_BODY).encode()
        mid = max(1, len(body) // 2)
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            stream=_TrickleStream([body[:mid], body[mid:]], delay_s=self._delay_s),
        )


async def test_deadline_releases_hold_without_debit(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await make_dev_principal(client, display_name="Deadline", roles=("internal",))
    project_id = await create_owned_project(client, actor_id, "session-turn-deadline")
    before = await _checkpoint_count(session_factory, project_id)
    transport = _TrickleTransport(delay_s=0.4)
    env = {GATEWAY_TOKEN_ENV: "gw-secret", TURN_TIMEOUT_ENV: "0.15"}
    owner = open_session(
        project_id,
        session_factory=session_factory,
        env=env,
        actor_env=_actor_env(actor_id),
    )
    app = create_metered_gateway_app(
        owner,
        env=env,
        gateway=GatewayClient(
            api_key="sk-test",
            base_url="https://openrouter.ai/api/v1",
            transport=transport,
            env=env,
        ),
    )
    refused = await _complete(app)
    assert refused.status_code == 422, refused.text
    payload = refused.json()
    assert REASON_TURN_DEADLINE in payload["error"]
    assert "may still bill" in payload["error"]
    assert payload["tokens_used"] == 0
    assert payload["minted"] is False
    assert transport.calls == 1
    assert len(await _debit_rows(session_factory, project_id)) == 0
    notes = await _adjustment_notes(session_factory, project_id)
    assert any(HOLD_NOTES in row for row in notes)
    assert any("daily_cap_release" in row for row in notes)
    async with session_factory() as session:
        assert await harness_tokens_used_today(session, UUID(project_id)) == 0
    assert await _checkpoint_count(session_factory, project_id) == before


async def test_stream_refuses_before_authorize_or_provider(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await make_dev_principal(client, display_name="Stream", roles=("internal",))
    project_id = await create_owned_project(client, actor_id, "session-stream-refuse")
    before = await _checkpoint_count(session_factory, project_id)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        calls["n"] += 1
        raise AssertionError("truthy stream must not reach OpenRouter")

    owner = open_session(
        project_id,
        session_factory=session_factory,
        actor_env=_actor_env(actor_id),
    )
    app = create_metered_gateway_app(
        owner,
        env={GATEWAY_TOKEN_ENV: "gw-secret"},
        gateway=_gateway(handler),
    )
    refused = await _complete(app, extra={"stream": True})
    assert refused.status_code == 422, refused.text
    payload = refused.json()
    assert payload["error"] == REASON_STREAM
    assert payload["tokens_used"] == 0
    assert payload["minted"] is False
    assert calls["n"] == 0
    assert len(await _debit_rows(session_factory, project_id)) == 0
    assert await _adjustment_notes(session_factory, project_id) == []
    async with session_factory() as session:
        assert await harness_tokens_used_today(session, UUID(project_id)) == 0
    assert await _checkpoint_count(session_factory, project_id) == before
