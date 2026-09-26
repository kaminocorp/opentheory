"""P0 — membership on original ledger write surfaces (assessment R1).

DB-free gates run in the default suite: unauthenticated POSTs are ``401`` before
any DB access. DB-backed tests skip without ``TEST_DATABASE_URL``: a signed-in
non-member is ``403`` and mints nothing.
"""

from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import settings
from app.models.checkpoint import Checkpoint
from app.schemas.claim import ClaimCreate
from app.services.claims import claim_is_open_work
from app.services.orchestration import _policy_from_reservation
from tests.principals import create_owned_project, make_dev_principal

_BOGUS = "00000000-0000-0000-0000-000000000000"


# --- DB-free: auth + schema gates ------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("post", f"/api/v1/projects/{_BOGUS}/checkpoints", {"summary": "x"}),
        ("post", f"/api/v1/projects/{_BOGUS}/threads", {"title": "T", "question": "q?"}),
        ("post", f"/api/v1/threads/{_BOGUS}/claims", {"kind": "hypothesis", "statement": "X"}),
        (
            "post",
            f"/api/v1/projects/{_BOGUS}/validations",
            {"target_type": "claim", "target_id": _BOGUS, "outcome": "passed"},
        ),
        (
            "post",
            f"/api/v1/claims/{_BOGUS}/evidence",
            {"title": "E", "source_type": "paper", "relation_kind": "support"},
        ),
        (
            "post",
            f"/api/v1/projects/{_BOGUS}/branches",
            {"name": "alt", "from_checkpoint_id": _BOGUS},
        ),
        (
            "post",
            f"/api/v1/branches/{_BOGUS}/close",
            {"outcome": "dead_end", "reason": "done"},
        ),
        (
            "post",
            f"/api/v1/projects/{_BOGUS}/merges",
            {"source_branch_ids": [_BOGUS], "resolution": "clean", "summary": "merge"},
        ),
        (
            "post",
            f"/api/v1/projects/{_BOGUS}/tags",
            {"name": "v1", "kind": "milestone", "checkpoint_id": _BOGUS},
        ),
        (
            "post",
            f"/api/v1/projects/{_BOGUS}/funding",
            {"amount": "1.00", "currency": "USD", "kind": "top_up", "source": "native"},
        ),
    ],
)
def test_unauthenticated_ledger_write_is_401(
    dbfree_client: TestClient, monkeypatch: pytest.MonkeyPatch, method: str, path: str, body: dict
) -> None:
    monkeypatch.setattr(settings, "auth_dev_header_enabled", False)
    resp = getattr(dbfree_client, method)(path, json=body)
    assert resp.status_code == 401, resp.text


def test_claim_create_rejects_client_stamped_status() -> None:
    with pytest.raises(ValidationError):
        ClaimCreate.model_validate(
            {"kind": "hypothesis", "statement": "X holds.", "status": "validated"}
        )


def test_claim_create_rejects_client_stamped_confidence() -> None:
    with pytest.raises(ValidationError):
        ClaimCreate.model_validate(
            {"kind": "hypothesis", "statement": "X holds.", "confidence": 0.99}
        )


def test_claim_create_accepts_statement_only() -> None:
    payload = ClaimCreate.model_validate({"kind": "hypothesis", "statement": "X holds."})
    dumped = payload.model_dump()
    assert "status" not in dumped
    assert "confidence" not in dumped


def test_validated_signal_is_not_open_work() -> None:
    assert claim_is_open_work("validated") is False
    assert claim_is_open_work("none") is True
    assert claim_is_open_work("contested") is True


def test_policy_from_reservation_uses_the_hold_rate_not_the_catalog() -> None:
    from decimal import Decimal
    from types import SimpleNamespace

    # A reserved slice billed at the live quote (9.99) must not be re-priced at
    # the blended catalog/settings rate when the mid-pass policy is built.
    row = SimpleNamespace(reserved_amount=Decimal("2.50"), model="anthropic/claude-sonnet-4")
    policy = _policy_from_reservation(row, Decimal("9.99"))  # type: ignore[arg-type]
    assert policy is not None
    assert policy.rate_per_1k == Decimal("9.99")


# --- DB-backed: non-member 403 + open-claims settlement -----------------------------


async def test_non_member_cannot_write_another_projects_ledger(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    owner_id = await make_dev_principal(client, display_name="Owner")
    project_id = await create_owned_project(client, owner_id, "mem-p0")
    thread = await client.post(
        f"/api/v1/projects/{project_id}/threads",
        json={"title": "T", "question": "q?"},
        headers={"X-Dev-Actor-Id": owner_id},
    )
    assert thread.status_code == 201, thread.text
    thread_id = thread.json()["id"]
    claim = await client.post(
        f"/api/v1/threads/{thread_id}/claims",
        json={"kind": "hypothesis", "statement": "X holds."},
        headers={"X-Dev-Actor-Id": owner_id},
    )
    assert claim.status_code == 201, claim.text
    claim_id = claim.json()["id"]
    seed = await client.post(
        f"/api/v1/projects/{project_id}/checkpoints",
        json={"summary": "seed", "thread_id": thread_id},
        headers={"X-Dev-Actor-Id": owner_id},
    )
    assert seed.status_code == 201, seed.text
    checkpoint_id = seed.json()["id"]

    outsider_id = await make_dev_principal(client, display_name="Outsider")

    attempts = [
        (
            "post",
            f"/api/v1/projects/{project_id}/checkpoints",
            {"summary": "intrusion"},
        ),
        (
            "post",
            f"/api/v1/projects/{project_id}/threads",
            {"title": "Nope", "question": "no?"},
        ),
        (
            "post",
            f"/api/v1/threads/{thread_id}/claims",
            {"kind": "hypothesis", "statement": "Forged."},
        ),
        (
            "post",
            f"/api/v1/projects/{project_id}/validations",
            {"target_type": "claim", "target_id": claim_id, "outcome": "passed"},
        ),
        (
            "post",
            f"/api/v1/claims/{claim_id}/evidence",
            {"title": "Forged", "source_type": "paper", "relation_kind": "support"},
        ),
        (
            "post",
            f"/api/v1/projects/{project_id}/branches",
            {"name": "stolen", "from_checkpoint_id": checkpoint_id},
        ),
        (
            "post",
            f"/api/v1/projects/{project_id}/tags",
            {"name": "stolen", "kind": "milestone", "checkpoint_id": checkpoint_id},
        ),
        (
            "post",
            f"/api/v1/projects/{project_id}/funding",
            {"amount": "1.00", "currency": "USD", "kind": "top_up", "source": "native"},
        ),
    ]
    branch = await client.post(
        f"/api/v1/projects/{project_id}/branches",
        json={"name": "alt", "from_checkpoint_id": checkpoint_id},
        headers={"X-Dev-Actor-Id": owner_id},
    )
    assert branch.status_code == 201, branch.text
    branch_id = branch.json()["id"]
    attempts.extend(
        [
            (
                "post",
                f"/api/v1/branches/{branch_id}/close",
                {"outcome": "dead_end", "reason": "nope"},
            ),
            (
                "post",
                f"/api/v1/projects/{project_id}/merges",
                {
                    "source_branch_ids": [branch_id],
                    "resolution": "clean",
                    "summary": "stolen merge",
                },
            ),
        ]
    )
    for method, path, body in attempts:
        resp = await getattr(client, method)(
            path, json=body, headers={"X-Dev-Actor-Id": outsider_id}
        )
        assert resp.status_code == 403, f"{path} -> {resp.status_code} {resp.text}"

    async with session_factory() as session:
        # Owner's seed + the fork checkpoint. Outsider writes minted nothing.
        count = (
            await session.execute(
                select(func.count()).select_from(Checkpoint).where(
                    Checkpoint.project_id == UUID(project_id)
                )
            )
        ).scalar()
        assert count == 2


async def test_validation_removes_claim_from_open_claims(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    from app.services.claims import open_claims_for_planner

    owner_id = await make_dev_principal(client, display_name="Owner")
    project_id = await create_owned_project(client, owner_id, "mem-open-claims")
    thread = await client.post(
        f"/api/v1/projects/{project_id}/threads",
        json={"title": "T", "question": "q?"},
        headers={"X-Dev-Actor-Id": owner_id},
    )
    assert thread.status_code == 201, thread.text
    thread_id = thread.json()["id"]
    claim = await client.post(
        f"/api/v1/threads/{thread_id}/claims",
        json={"kind": "hypothesis", "statement": "X holds."},
        headers={"X-Dev-Actor-Id": owner_id},
    )
    assert claim.status_code == 201, claim.text
    claim_id = claim.json()["id"]
    assert claim.json()["status"] == "proposed"
    assert claim.json()["signal"] == "none"

    async with session_factory() as session:
        before = await open_claims_for_planner(session, UUID(thread_id))
        assert [str(c.id) for c in before] == [claim_id]

    validated = await client.post(
        f"/api/v1/projects/{project_id}/validations",
        json={"target_type": "claim", "target_id": claim_id, "outcome": "passed"},
        headers={"X-Dev-Actor-Id": owner_id},
    )
    assert validated.status_code == 201, validated.text

    after_read = await client.get(f"/api/v1/claims/{claim_id}")
    assert after_read.status_code == 200
    assert after_read.json()["status"] == "proposed"  # column stays create-time
    assert after_read.json()["signal"] == "validated"

    async with session_factory() as session:
        after = await open_claims_for_planner(session, UUID(thread_id))
        assert after == []
