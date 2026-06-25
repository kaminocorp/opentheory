"""DB-backed tests for the 0.6.3 funding write path.

Covers: native funding by an internal actor (one settled ``FundingAllocation`` + one ``fund``
``Contribution`` with ``funding_allocation_id`` set and ``checkpoint_id`` NULL, and **no minted
checkpoint** — locks Decision #3); the native-funding ``internal``-role gate (403) and the
unauthenticated path (401); stripe funding born ``pending`` and excluded from ``funded``;
append-only ORM enforcement on ``FundingAllocation``; the budget read model; and the
funder/contributor/validator separation. These run only when a database is configured.
"""

from decimal import Decimal
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import settings
from app.models import AppendOnlyError
from app.models.checkpoint import Checkpoint
from app.models.contribution import Contribution
from app.models.enums import FundingKind, FundingSource, FundingStatus
from app.models.funding import FundingAllocation
from app.models.validation import Validation


async def _internal_actor(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/actors",
        json={"type": "human", "display_name": "Kamino", "roles": ["internal"]},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _actor(client: AsyncClient) -> str:
    resp = await client.post("/api/v1/actors", json={"type": "human", "display_name": "Ada"})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _project(client: AsyncClient, slug: str = "funding-project") -> str:
    # Project creation now requires an acting actor; bootstrap a dev actor for the header.
    actor = await client.post(
        "/api/v1/actors", json={"type": "human", "display_name": "Author"}
    )
    assert actor.status_code == 201, actor.text
    resp = await client.post(
        "/api/v1/projects",
        json={"title": "Funding Project", "slug": slug, "question": "What is X?"},
        headers={"X-Dev-Actor-Id": actor.json()["id"]},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _fund(
    client: AsyncClient,
    project_id: str,
    actor_id: str | None,
    *,
    amount: str = "100.00",
    currency: str = "USD",
    kind: str = "top_up",
    source: str = "native",
) -> tuple[int, dict]:
    headers = {"X-Dev-Actor-Id": actor_id} if actor_id else {}
    resp = await client.post(
        f"/api/v1/projects/{project_id}/funding",
        json={"amount": amount, "currency": currency, "kind": kind, "source": source},
        headers=headers,
    )
    return resp.status_code, (resp.json() if resp.content else {})


def _dec(value) -> Decimal:
    """Tolerant of Decimal-as-string or Decimal-as-number JSON encodings."""
    return Decimal(str(value))


async def test_native_funding_records_settled_allocation_and_fund_contribution(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await _internal_actor(client)
    project_id = await _project(client)

    code, body = await _fund(client, project_id, actor_id, amount="500.00", source="native")
    assert code == 201, body
    assert body["source"] == "native"
    assert body["status"] == "settled"
    assert _dec(body["amount"]) == Decimal("500.00")
    assert body["actor"]["id"] == actor_id
    allocation_id = body["id"]

    async with session_factory() as session:
        allocations = (await session.execute(select(FundingAllocation))).scalars().all()
        assert len(allocations) == 1
        assert str(allocations[0].id) == allocation_id

        # One `fund` contribution: linked to the allocation, NOT to a checkpoint (Decision #3).
        contribs = (await session.execute(select(Contribution))).scalars().all()
        assert len(contribs) == 1
        assert contribs[0].action == "fund"
        assert str(contribs[0].funding_allocation_id) == allocation_id
        assert contribs[0].checkpoint_id is None

        # No research checkpoint was minted for the funding event (the research DAG is untouched).
        checkpoints = (await session.execute(select(Checkpoint))).scalars().all()
        assert len(checkpoints) == 0


async def test_native_funding_requires_internal_role(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await _actor(client)  # not internal
    project_id = await _project(client)

    code, body = await _fund(client, project_id, actor_id, source="native")
    assert code == 403, body

    # Nothing was written.
    async with session_factory() as session:
        allocations = (await session.execute(select(FundingAllocation))).scalars().all()
        assert allocations == []


async def test_unauthenticated_funding_rejected(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Create the project while the dev-header path is still enabled, then turn it OFF to
    # assert the production posture: no credentials -> 401 on the funding write.
    project_id = await _project(client)
    monkeypatch.setattr(settings, "auth_dev_header_enabled", False)
    code, _ = await _fund(client, project_id, None, source="native")
    assert code == 401


async def test_stripe_funding_via_api_is_rejected(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    # Stripe funding has no settlement path until 0.7.0, so the create path accepts only native
    # (0.6.2 hardening): an authenticated actor cannot write a `pending` stripe allocation into the
    # public funding history. The model + enum stay so 0.7.0 can activate it.
    internal_id = await _internal_actor(client)
    project_id = await _project(client)

    code, body = await _fund(client, project_id, internal_id, amount="250.00", source="stripe")
    assert code == 422, body

    async with session_factory() as session:
        allocations = (await session.execute(select(FundingAllocation))).scalars().all()
        assert allocations == []  # nothing written


async def test_pending_allocation_excluded_from_funded(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    # The budget counts only *settled* funding toward `funded`/`available`, while `by_status`
    # tallies every status and `by_source` is settled-only. Pending funding is no longer creatable
    # over HTTP (stripe is rejected), so insert a pending allocation directly to exercise the
    # exclusion the budget read model guarantees.
    internal_id = await _internal_actor(client)
    project_id = await _project(client)

    code, body = await _fund(client, project_id, internal_id, amount="500.00", source="native")
    assert code == 201, body

    async with session_factory() as session:
        session.add(
            FundingAllocation(
                project_id=UUID(project_id),
                actor_id=UUID(internal_id),
                amount=Decimal("250.00"),
                currency="USD",
                kind=FundingKind.TOP_UP,
                source=FundingSource.STRIPE,
                status=FundingStatus.PENDING,
            )
        )
        await session.commit()

    budget = (await client.get(f"/api/v1/projects/{project_id}/budget")).json()
    assert _dec(budget["funded"]) == Decimal("500.00")  # only settled counts
    assert _dec(budget["spent"]) == Decimal("0")
    assert _dec(budget["available"]) == Decimal("500.00")
    assert _dec(budget["by_source"]["native"]) == Decimal("500.00")
    assert "stripe" not in budget["by_source"]  # by_source is settled-only
    assert _dec(budget["by_status"]["settled"]) == Decimal("500.00")
    assert _dec(budget["by_status"]["pending"]) == Decimal("250.00")


async def test_funding_allocation_is_append_only(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    actor_id = await _internal_actor(client)
    project_id = await _project(client)
    code, body = await _fund(client, project_id, actor_id, source="native")
    assert code == 201, body
    allocation_id = body["id"]

    async with session_factory() as session:
        allocation = await session.get(FundingAllocation, allocation_id)
        assert allocation is not None
        allocation.notes = "amended"
        with pytest.raises(AppendOnlyError, match="append-only"):
            await session.flush()

    async with session_factory() as session:
        allocation = await session.get(FundingAllocation, allocation_id)
        await session.delete(allocation)
        with pytest.raises(AppendOnlyError):
            await session.flush()

    async with session_factory() as session:
        assert await session.get(FundingAllocation, allocation_id) is not None


async def test_budget_and_overview_reflect_settled_funding(client: AsyncClient) -> None:
    actor_id = await _internal_actor(client)
    project_id = await _project(client)
    await _fund(client, project_id, actor_id, amount="100.00", source="native")
    await _fund(client, project_id, actor_id, amount="50.00", source="native")

    budget = (await client.get(f"/api/v1/projects/{project_id}/budget")).json()
    assert _dec(budget["funded"]) == Decimal("150.00")
    assert _dec(budget["available"]) == Decimal("150.00")
    assert budget["currency"] == "USD"

    overview = (await client.get(f"/api/v1/projects/{project_id}/overview")).json()
    assert overview["budget"] is not None
    assert _dec(overview["budget"]["funded"]) == Decimal("150.00")


async def test_funding_lists_and_detail(client: AsyncClient) -> None:
    actor_id = await _internal_actor(client)
    project_id = await _project(client)
    _, body = await _fund(client, project_id, actor_id, source="native")
    allocation_id = body["id"]

    listing = await client.get(f"/api/v1/projects/{project_id}/funding")
    assert listing.status_code == 200
    assert [a["id"] for a in listing.json()] == [allocation_id]

    detail = await client.get(f"/api/v1/funding/{allocation_id}")
    assert detail.status_code == 200
    assert detail.json()["id"] == allocation_id


async def test_funding_is_not_contribution_or_validation(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    """Funder/contributor/validator separation: funding grants budget and nothing else."""
    actor_id = await _internal_actor(client)
    project_id = await _project(client)
    await _fund(client, project_id, actor_id, source="native")

    async with session_factory() as session:
        contribs = (await session.execute(select(Contribution))).scalars().all()
        # Exactly one contribution, and it is a `fund` — no authorship/validation contribution.
        assert {c.action for c in contribs} == {"fund"}

        # No validation was created; funding confers no validation authority.
        validations = (await session.execute(select(Validation))).scalars().all()
        assert validations == []
