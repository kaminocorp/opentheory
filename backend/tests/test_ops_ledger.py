"""DB-backed ops dashboard reads. Skip without TEST_DATABASE_URL."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.checkpoint import Checkpoint
from app.models.compute_debit import ComputeDebit
from app.models.enums import ComputeDebitKind, ComputeDebitRateSource
from app.services.harness_meter import SESSION_NOTES, hold_notes, release_notes, spend_notes
from tests.principals import create_owned_project, make_dev_principal


async def _checkpoint_count(session_factory: async_sessionmaker, project_id: str) -> int:
    async with session_factory() as session:
        result = await session.execute(
            select(func.count()).select_from(Checkpoint).where(
                Checkpoint.project_id == UUID(project_id)
            )
        )
        return int(result.scalar_one() or 0)


async def _add_debit(
    session_factory: async_sessionmaker,
    project_id: str,
    *,
    tokens_used: int,
    amount: Decimal = Decimal("0"),
    notes: str | None = None,
) -> None:
    async with session_factory() as session:
        session.add(
            ComputeDebit(
                project_id=UUID(project_id),
                tokens_used=tokens_used,
                amount=amount,
                currency="USD",
                rate_per_1k=Decimal("0"),
                rate_source=ComputeDebitRateSource.BLENDED_FALLBACK,
                kind=ComputeDebitKind.PLANNING,
                notes=notes,
            )
        )
        await session.commit()


async def test_ops_missing_project_is_404(client: AsyncClient) -> None:
    missing = uuid4()
    resp = await client.get(f"/api/v1/projects/{missing}/ops")
    assert resp.status_code == 404


async def test_ops_empty_project_is_honest_unfunded(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await make_dev_principal(client, display_name="Ada")
    project_id = await create_owned_project(client, actor_id, "ops-empty")
    before = await _checkpoint_count(session_factory, project_id)

    resp = await client.get(f"/api/v1/projects/{project_id}/ops")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["project_id"] == project_id
    assert body["notes_prefix"] == SESSION_NOTES
    assert body["budget"]["state"] == "unfunded"
    assert Decimal(body["budget"]["snapshot"]["funded"]) == Decimal("0")
    assert "not exhausted" in body["budget"]["note"]
    assert body["daily_cap"]["tokens_used_today"] == 0
    assert body["daily_cap"]["cap"] == 20_000
    assert body["daily_cap"]["cap_source"] == "default"
    assert body["daily_cap"]["remaining"] == 20_000
    assert body["daily_cap"]["exhausted"] is False
    assert body["holds"] == []
    assert body["recent_turns"] == []
    assert body["last_turn"] is None
    assert body["refusals"]["recorded"] is False
    assert body["enablement"]["loop"]["enabled"] is False
    assert body["enablement"]["gateway"]["enabled"] == "unknown"
    assert body["enablement"]["mcp_child"]["enabled"] == "unknown"
    assert await _checkpoint_count(session_factory, project_id) == before


async def test_ops_reads_harness_ledger_and_ignores_other_spend(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await make_dev_principal(client, display_name="Ada", roles=("internal",))
    project_id = await create_owned_project(client, actor_id, "ops-meter")
    funded = await client.post(
        f"/api/v1/projects/{project_id}/funding",
        json={"amount": "25.00", "currency": "USD", "kind": "top_up", "source": "native"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert funded.status_code == 201, funded.text

    hold_id = uuid4()
    await _add_debit(
        session_factory,
        project_id,
        tokens_used=80,
        amount=Decimal("0.40"),
        notes=f"{SESSION_NOTES}; rate fallback: blended_fallback",
    )
    await _add_debit(
        session_factory,
        project_id,
        tokens_used=500,
        amount=Decimal("0"),
        notes=hold_notes(hold_id),
    )
    await _add_debit(
        session_factory,
        project_id,
        tokens_used=-500,
        amount=Decimal("0"),
        notes=release_notes(hold_id),
    )
    await _add_debit(
        session_factory,
        project_id,
        tokens_used=9_999,
        amount=Decimal("5"),
        notes="agent_pass; not a harness turn",
    )
    # Underscore in the prefix is not a LIKE wildcard — this sibling must not count.
    await _add_debit(
        session_factory,
        project_id,
        tokens_used=7_000,
        amount=Decimal("1"),
        notes="harnessXsession_turn; decoy",
    )

    before = await _checkpoint_count(session_factory, project_id)
    resp = await client.get(f"/api/v1/projects/{project_id}/ops")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["budget"]["state"] == "available"
    assert Decimal(body["budget"]["snapshot"]["funded"]) == Decimal("25.00")
    assert body["daily_cap"]["tokens_used_today"] == 80
    assert body["daily_cap"]["remaining"] == 20_000 - 80
    assert body["daily_cap"]["exhausted"] is False
    assert len(body["holds"]) == 1
    assert body["holds"][0]["hold_id"] == str(hold_id)
    assert body["holds"][0]["status"] == "released"
    assert body["holds"][0]["tokens"] == 500
    assert body["holds"][0]["stale"] is None
    kinds = {row["kind"] for row in body["recent_turns"]}
    assert kinds == {"spend", "hold", "release"}
    assert all(
        (row["notes"] or "").startswith(SESSION_NOTES) for row in body["recent_turns"]
    )
    assert body["refusals"]["recorded"] is False
    assert await _checkpoint_count(session_factory, project_id) == before


async def test_ops_open_hold_and_exhausted_pot(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await make_dev_principal(client, display_name="Ada", roles=("internal",))
    project_id = await create_owned_project(client, actor_id, "ops-hold")
    funded = await client.post(
        f"/api/v1/projects/{project_id}/funding",
        json={"amount": "1.00", "currency": "USD", "kind": "top_up", "source": "native"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert funded.status_code == 201, funded.text
    await _add_debit(
        session_factory,
        project_id,
        tokens_used=200,
        amount=Decimal("1.00"),
        notes=f"{SESSION_NOTES}; billed",
    )
    open_id = uuid4()
    await _add_debit(
        session_factory,
        project_id,
        tokens_used=19_800,
        amount=Decimal("0"),
        notes=hold_notes(open_id),
    )

    resp = await client.get(f"/api/v1/projects/{project_id}/ops")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["budget"]["state"] == "exhausted"
    assert "Unfunded is a different state" in body["budget"]["note"]
    assert body["daily_cap"]["tokens_used_today"] == 20_000
    assert body["daily_cap"]["remaining"] == 0
    assert body["daily_cap"]["exhausted"] is True
    assert len(body["holds"]) == 1
    assert body["holds"][0]["status"] == "open"
    assert body["holds"][0]["hold_id"] == str(open_id)
    assert body["holds"][0]["stale"] is False


async def test_ops_last_turn_surfaces_clamp_and_overshoot(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await make_dev_principal(client, display_name="Ada")
    project_id = await create_owned_project(client, actor_id, "ops-last-turn")
    await _add_debit(
        session_factory,
        project_id,
        tokens_used=80,
        amount=Decimal("0.40"),
        notes=spend_notes(clamp=50, overshoot=30, price_known=True, pot_room=50),
    )
    resp = await client.get(f"/api/v1/projects/{project_id}/ops")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    last = body["last_turn"]
    assert last is not None
    assert last["tokens_used"] == 80
    assert last["clamp"] == 50
    assert last["overshoot"] == 30
    assert last["price_known"] is True
    assert last["pot_room"] == 50
    assert "overshoot 30" in last["note"]
    assert "min of daily room and pot room" in last["note"]
    spend = next(row for row in body["recent_turns"] if row["kind"] == "spend")
    assert spend["clamp"] == 50
    assert spend["overshoot"] == 30
    assert spend["price_known"] is True
    assert spend["pot_room"] == 50


async def test_ops_last_turn_does_not_claim_unused_pot_room(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await make_dev_principal(client, display_name="Bea")
    project_id = await create_owned_project(client, actor_id, "ops-last-turn-unfunded")
    await _add_debit(
        session_factory,
        project_id,
        tokens_used=20,
        amount=Decimal("0.10"),
        notes=spend_notes(clamp=80, price_known=True),
    )
    resp = await client.get(f"/api/v1/projects/{project_id}/ops")
    assert resp.status_code == 200, resp.text
    last = resp.json()["last_turn"]
    assert last is not None
    assert last["price_known"] is True
    assert last["pot_room"] is None
    assert last["clamp"] == 80
    assert "pot room was not applied" in last["note"]
    assert "min of daily room and pot room" not in last["note"]
