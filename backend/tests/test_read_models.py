"""DB-backed tests for the 0.3.4 enriched read models.

Covers the project overview aggregate counts, the per-thread claim count on the thread
list, and the enriched checkpoint read (creating actor, contribution kind, and
referenced claim/evidence labels). Skip when no database is configured (see conftest.py).

0.16.0 adds the claim **grounding** round-trips: each instrument run through the real
``run_instrument`` chokepoint, asserted through the HTTP claim read. The aggregation *rules* are
pinned DB-free in ``tests/test_grounding.py``; what these prove is the part only a database can —
that the chain ``ClaimEvidenceLink → Evidence.evidence_metadata`` the read model traverses is
actually what the write path lays down.
"""

from uuid import UUID

from httpx import AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.models.actor import Actor
from app.services.tool_runs import run_instrument
from app.toolbench.instruments import (
    CALC_EVAL,
    COORDINATE_MEASURE,
    COUNTEREXAMPLE_SEARCH,
    EXPR_COMPARE,
    Z3_PROVE,
)


async def _actor(client: AsyncClient, name: str = "Ada") -> str:
    resp = await client.post("/api/v1/actors", json={"type": "human", "display_name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _project(client: AsyncClient, slug: str = "test-project") -> str:
    # Project creation now requires an acting actor; bootstrap a dev actor for the header.
    actor = await client.post(
        "/api/v1/actors", json={"type": "human", "display_name": "Author"}
    )
    assert actor.status_code == 201, actor.text
    resp = await client.post(
        "/api/v1/projects",
        json={"title": "Test Project", "slug": slug, "question": "What is X?"},
        headers={"X-Dev-Actor-Id": actor.json()["id"]},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _thread(client: AsyncClient, project_id: str, actor_id: str, title: str = "T") -> str:
    resp = await client.post(
        f"/api/v1/projects/{project_id}/threads",
        json={"title": title, "question": "q?"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _claim(client: AsyncClient, thread_id: str, actor_id: str, statement: str) -> str:
    resp = await client.post(
        f"/api/v1/threads/{thread_id}/claims",
        json={"kind": "hypothesis", "statement": statement},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _evidence(client: AsyncClient, claim_id: str, actor_id: str, title: str) -> str:
    resp = await client.post(
        f"/api/v1/claims/{claim_id}/evidence",
        json={"title": title, "source_type": "paper", "relation_kind": "support"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _checkpoint(client: AsyncClient, project_id: str, actor_id: str) -> str:
    resp = await client.post(
        f"/api/v1/projects/{project_id}/checkpoints",
        json={"summary": "a checkpoint"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _validate(
    client: AsyncClient, project_id: str, actor_id: str, claim_id: str, outcome: str
) -> None:
    resp = await client.post(
        f"/api/v1/projects/{project_id}/validations",
        json={"target_type": "claim", "target_id": claim_id, "outcome": outcome},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert resp.status_code == 201, resp.text


async def _branch(
    client: AsyncClient, project_id: str, actor_id: str, from_checkpoint: str
) -> str:
    resp = await client.post(
        f"/api/v1/projects/{project_id}/branches",
        json={"from_checkpoint_id": from_checkpoint, "name": "alt"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_project_overview_counts(client: AsyncClient) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client)
    thread_a = await _thread(client, project_id, actor_id, "A")
    await _thread(client, project_id, actor_id, "B")
    claim_id = await _claim(client, thread_a, actor_id, "X causes Y")
    await _evidence(client, claim_id, actor_id, "Smith 2024")
    await client.post(
        f"/api/v1/projects/{project_id}/checkpoints",
        json={"summary": "first move"},
        headers={"X-Dev-Actor-Id": actor_id},
    )

    overview = await client.get(f"/api/v1/projects/{project_id}/overview")
    assert overview.status_code == 200, overview.text
    body = overview.json()
    assert body["id"] == project_id
    assert body["title"] == "Test Project"
    assert body["counts"] == {
        "threads": 2,
        "claims": 1,
        "evidence": 1,
        "checkpoints": 1,
        "validations": 0,
        "branches": 0,
    }


async def test_overview_missing_project_404(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/projects/00000000-0000-0000-0000-000000000000/overview")
    assert resp.status_code == 404


async def test_thread_list_includes_claim_count(client: AsyncClient) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client)
    busy = await _thread(client, project_id, actor_id, "busy")
    await _thread(client, project_id, actor_id, "empty")
    await _claim(client, busy, actor_id, "c1")
    await _claim(client, busy, actor_id, "c2")

    listed = await client.get(f"/api/v1/projects/{project_id}/threads")
    assert listed.status_code == 200, listed.text
    by_title = {t["title"]: t["claim_count"] for t in listed.json()}
    assert by_title == {"busy": 2, "empty": 0}


async def test_checkpoint_read_is_enriched(client: AsyncClient) -> None:
    actor_id = await _actor(client, name="Grace")
    project_id = await _project(client)
    thread_id = await _thread(client, project_id, actor_id)
    claim_id = await _claim(client, thread_id, actor_id, "X is caused by Y")
    evidence_id = await _evidence(client, claim_id, actor_id, "Smith 2024")

    created = await client.post(
        f"/api/v1/projects/{project_id}/checkpoints",
        json={
            "thread_id": thread_id,
            "summary": "Recorded claim with evidence",
            "refs": [
                {"target_type": "claim", "target_id": claim_id, "role": "asserted"},
                {"target_type": "evidence", "target_id": evidence_id, "role": "cited"},
            ],
        },
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert created.status_code == 201, created.text
    checkpoint_id = created.json()["id"]

    detail = await client.get(f"/api/v1/checkpoints/{checkpoint_id}")
    assert detail.status_code == 200, detail.text
    body = detail.json()

    # creating actor
    assert body["author"] is not None
    assert body["author"]["display_name"] == "Grace"
    assert body["author"]["type"] == "human"
    # contribution kind recorded for this checkpoint
    assert body["contribution_kind"] == "create_checkpoint"
    # referenced primitive labels resolved server-side
    labels = {ref["target_type"]: ref["label"] for ref in body["refs"]}
    assert labels == {"claim": "X is caused by Y", "evidence": "Smith 2024"}

    # the same enrichment is present in the project listing
    listed = await client.get(f"/api/v1/projects/{project_id}/checkpoints")
    assert listed.status_code == 200
    assert listed.json()[0]["author"]["display_name"] == "Grace"


async def test_claim_read_validation_history_and_signal(client: AsyncClient) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client)
    thread_id = await _thread(client, project_id, actor_id)
    passing = await _claim(client, thread_id, actor_id, "well-supported claim")
    contested = await _claim(client, thread_id, actor_id, "shaky claim")

    await _validate(client, project_id, actor_id, passing, "passed")
    await _validate(client, project_id, actor_id, contested, "contradicts")

    listed = (await client.get(f"/api/v1/threads/{thread_id}/claims")).json()
    claims = {c["statement"]: c for c in listed}
    assert claims["well-supported claim"]["signal"] == "validated"
    assert len(claims["well-supported claim"]["validations"]) == 1
    assert claims["well-supported claim"]["validations"][0]["outcome"] == "passed"
    assert claims["shaky claim"]["signal"] == "contested"

    # A retract clears the contradiction (Decision #5 derivation, no status mutation).
    await _validate(client, project_id, actor_id, contested, "retract")
    detail = await client.get(f"/api/v1/claims/{contested}")
    assert detail.status_code == 200
    assert detail.json()["signal"] != "contested"
    assert len(detail.json()["validations"]) == 2  # history preserved, oldest first
    assert detail.json()["validations"][0]["outcome"] == "contradicts"

    # A contradiction recorded *after* the retract re-contests the claim — the signal is
    # order-aware (the latest decisive event wins), not "any retract clears everything".
    await _validate(client, project_id, actor_id, contested, "contradicts")
    detail = await client.get(f"/api/v1/claims/{contested}")
    assert detail.json()["signal"] == "contested"
    assert len(detail.json()["validations"]) == 3


async def test_overview_branch_and_validation_summaries(client: AsyncClient) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client)
    thread_id = await _thread(client, project_id, actor_id)
    claim_id = await _claim(client, thread_id, actor_id, "contested claim")
    fork = await _checkpoint(client, project_id, actor_id)

    await _validate(client, project_id, actor_id, claim_id, "contradicts")  # mints a checkpoint
    branch_id = await _branch(client, project_id, actor_id, fork)  # mints a checkpoint, open
    await client.post(
        f"/api/v1/branches/{branch_id}/close",
        json={"outcome": "dead_end", "reason": "ruled out"},
        headers={"X-Dev-Actor-Id": actor_id},
    )

    overview = (await client.get(f"/api/v1/projects/{project_id}/overview")).json()
    assert overview["counts"]["validations"] == 1
    assert overview["counts"]["branches"] == 1
    assert overview["branch_counts"] == {"open": 0, "dead_end": 1, "closed": 0}
    # the contested claim surfaces in the contradictions summary
    assert [c["claim_id"] for c in overview["contradictions"]] == [claim_id]
    assert overview["contradictions"][0]["statement"] == "contested claim"


async def test_branch_list_includes_checkpoint_count(client: AsyncClient) -> None:
    actor_id = await _actor(client)
    project_id = await _project(client)
    fork = await _checkpoint(client, project_id, actor_id)
    # the fork checkpoint is recorded on the branch
    branch_id = await _branch(client, project_id, actor_id, fork)
    # add a second checkpoint on the branch
    resp = await client.post(
        f"/api/v1/projects/{project_id}/checkpoints",
        json={"summary": "on branch", "branch_id": branch_id},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert resp.status_code == 201, resp.text

    listed = await client.get(f"/api/v1/projects/{project_id}/branches")
    assert listed.status_code == 200
    rows = {b["id"]: b for b in listed.json()}
    assert rows[branch_id]["checkpoint_count"] == 2
    assert rows[branch_id]["status"] == "open"


# --- 0.16.0: claim grounding through the chokepoint -----------------------------------------------


async def _grounding(client: AsyncClient, claim_id: str) -> dict:
    """The claim's derived grounding, read back over HTTP (the shape the frontend consumes)."""
    detail = await client.get(f"/api/v1/claims/{claim_id}")
    assert detail.status_code == 200, detail.text
    return detail.json()["grounding"]


async def _run(
    session_factory: async_sessionmaker,
    project_id: str,
    actor_id: str,
    instrument,
    inputs: dict,
    claim_id: str | None = None,
    **kwargs,
):
    """Drive a real instrument through ``run_instrument`` (the same chokepoint humans use)."""
    async with session_factory() as session:
        actor = await session.get(Actor, UUID(actor_id))
        return await run_instrument(
            session,
            UUID(project_id),
            instrument,
            actor,
            inputs=inputs,
            claim_id=UUID(claim_id) if claim_id else None,
            **kwargs,
        )


async def test_z3_proof_grounds_a_claim_as_proven_without_any_validation(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    """Acceptance 1 — the gap this release closes.

    Before 0.16.0 a claim carrying a machine-checked proof read ``signal: "none"``, exactly like a
    claim carrying nothing but an opinion, until a human clicked *validate*. The proof is now
    visible
    on its own axis with **zero** validations recorded.
    """
    actor_id = await _actor(client)
    project_id = await _project(client, "ground-proven")
    thread_id = await _thread(client, project_id, actor_id)
    claim_id = await _claim(client, thread_id, actor_id, "x + y > 0 for positive x, y.")

    await _run(
        session_factory,
        project_id,
        actor_id,
        Z3_PROVE,
        {
            "variables": {"x": "real", "y": "real"},
            "constraints": ["x > 0", "y > 0"],
            "goal": "x + y > 0",
        },
        claim_id,
    )

    detail = (await client.get(f"/api/v1/claims/{claim_id}")).json()
    assert detail["grounding"] == {
        "support": "A",
        "counter": None,
        "cited": False,
        "headline": "proven",
    }
    # The two axes stay independent: no validation was recorded, so the validation signal is silent.
    assert detail["validations"] == []
    assert detail["signal"] == "none"


async def test_exact_counterexample_refutes_despite_supporting_runs(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    """Acceptance 2 (D8) — a counter at A/B dominates any amount of support, end to end."""
    actor_id = await _actor(client)
    project_id = await _project(client, "ground-refuted")
    thread_id = await _thread(client, project_id, actor_id)
    claim_id = await _claim(client, thread_id, actor_id, "x*x is never equal to x.")

    # Three supporting runs first…
    for expression in ("2**2 != 2", "3**2 != 3", "4**2 != 4"):
        await _run(
            session_factory, project_id, actor_id, CALC_EVAL, {"expression": expression}, claim_id
        )
    grounding = await _grounding(client, claim_id)
    assert grounding["headline"] == "B"

    # …then one machine-checked counter-model (x = 0), which settles it negatively.
    await _run(
        session_factory,
        project_id,
        actor_id,
        Z3_PROVE,
        {"variables": {"x": "int"}, "constraints": [], "goal": "x*x != x"},
        claim_id,
    )

    grounding = await _grounding(client, claim_id)
    assert grounding["counter"] == "A"
    assert grounding["support"] == "B"  # the support is reported, not erased
    assert grounding["headline"] == "refuted"


async def test_undecided_run_leaves_grounding_untouched(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    """Acceptance 3 (honesty rule 1) — an honest "could not decide" is not a weak pass.

    ``expr.compare`` on ``sqrt(x**2)`` vs ``x`` is the *deterministic* undecided: equivalent only
    under ``x > 0``, so without that assumption SymPy's ``is_zero`` is ``None`` and 0.9.6 makes it
    escalate rather than guess. (A Z3 ``unknown`` would be the other route, but Z3's nondeterminism
    makes it an unreliable fixture — the same reason 0.13.5 unit-tested that mapping directly.)
    """
    actor_id = await _actor(client)
    project_id = await _project(client, "ground-undecided")
    thread_id = await _thread(client, project_id, actor_id)
    claim_id = await _claim(client, thread_id, actor_id, "sqrt(x^2) = x")

    run = await _run(
        session_factory,
        project_id,
        actor_id,
        EXPR_COMPARE,
        {"left": "sqrt(x**2)", "right": "x"},
        claim_id,
    )
    assert run.status.value == "undecided"
    assert run.evidence_id is not None  # the run *was* recorded — it is a citable outcome

    grounding = await _grounding(client, claim_id)
    assert grounding == {
        "support": None,
        "counter": None,
        "cited": False,
        "headline": "ungrounded",
    }

    # The same comparison *under* the assumption that settles it climbs to B, proving the claim was
    # ungrounded because the outcome was undecided — not because the plumbing was inert.
    await _run(
        session_factory,
        project_id,
        actor_id,
        EXPR_COMPARE,
        {"left": "sqrt(x**2)", "right": "x"},
        claim_id,
        assumptions={"x": {"positive": True}},
    )
    assert (await _grounding(client, claim_id))["headline"] == "B"


async def test_hand_attached_evidence_grades_d(client: AsyncClient) -> None:
    """Acceptance 4 (honesty rule 2) — D is the absence of a tool, and it is a legitimate rung."""
    actor_id = await _actor(client)
    project_id = await _project(client, "ground-human")
    thread_id = await _thread(client, project_id, actor_id)
    claim_id = await _claim(client, thread_id, actor_id, "asserted, not computed")

    await _evidence(client, claim_id, actor_id, "A paper someone read")

    grounding = await _grounding(client, claim_id)
    assert grounding == {"support": "D", "counter": None, "cited": False, "headline": "D"}


async def test_finite_grid_support_grades_c_not_b(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    """The asymmetric row, proven through the real write path: sampling settles nothing."""
    actor_id = await _actor(client)
    project_id = await _project(client, "ground-sampled")
    thread_id = await _thread(client, project_id, actor_id)
    claim_id = await _claim(client, thread_id, actor_id, "a + b == b + a for small integers")

    await _run(
        session_factory,
        project_id,
        actor_id,
        COUNTEREXAMPLE_SEARCH,
        {
            "relation": "a + b == b + a",
            "variables": {"a": {"min": 1, "max": 3}, "b": {"min": 1, "max": 3}},
        },
        claim_id,
    )

    grounding = await _grounding(client, claim_id)
    assert grounding["support"] == "C"
    assert grounding["headline"] == "C"


async def test_grounding_does_not_mutate_claim_status_or_confidence(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    """Acceptance 6 (D6) — grounding is display-derived, exactly like ``signal``.

    A machine-checked proof must not silently promote ``status`` to ``validated`` or invent a
    ``confidence``: confidence stays explainable through history, never a value the system sets.
    """
    actor_id = await _actor(client)
    project_id = await _project(client, "ground-nomutate")
    thread_id = await _thread(client, project_id, actor_id)
    claim_id = await _claim(client, thread_id, actor_id, "status must not move")

    before = (await client.get(f"/api/v1/claims/{claim_id}")).json()

    await _run(
        session_factory,
        project_id,
        actor_id,
        COORDINATE_MEASURE,
        {
            "points": {"A": [0, 0], "B": [3, 0], "C": [3, 4]},
            "distances": [["A", "C"]],
            "angles": [["A", "B", "C"]],
        },
        claim_id,
    )

    after = (await client.get(f"/api/v1/claims/{claim_id}")).json()
    assert after["grounding"]["headline"] == "B"  # the derivation did happen…
    assert after["status"] == before["status"]  # …and changed nothing stored
    assert after["confidence"] == before["confidence"]
    assert before["status"] == "proposed"


async def test_claim_list_grounding_is_batch_loaded(
    client: AsyncClient, db_engine: AsyncEngine, session_factory: async_sessionmaker
) -> None:
    """Acceptance 7 — listing N claims costs a fixed number of queries, not one per claim.

    Asserted by counting SQL statements on the engine rather than by timing: the loader must stay a
    single ``IN``-query no matter how many claims are in the thread, mirroring the 0.4.4 constraint
    on ``validations_by_claim``.
    """
    actor_id = await _actor(client)
    project_id = await _project(client, "ground-batch")
    thread_id = await _thread(client, project_id, actor_id)
    claim_ids = [await _claim(client, thread_id, actor_id, f"claim {n}") for n in range(6)]
    # Ground half of them so the loader has real rows to aggregate, not just an empty result.
    for claim_id in claim_ids[:3]:
        await _run(
            session_factory, project_id, actor_id, CALC_EVAL, {"expression": "1 == 1"}, claim_id
        )

    statements: list[str] = []

    def _record(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        statements.append(statement)

    event.listen(db_engine.sync_engine, "before_cursor_execute", _record)
    try:
        listed = await client.get(f"/api/v1/threads/{thread_id}/claims")
    finally:
        event.remove(db_engine.sync_engine, "before_cursor_execute", _record)

    assert listed.status_code == 200
    body = listed.json()
    assert len(body) == 6
    assert sum(1 for c in body if c["grounding"]["headline"] == "B") == 3

    # One SELECT against claim_evidence_links for the whole page — never one per claim.
    link_queries = [s for s in statements if "claim_evidence_links" in s]
    assert len(link_queries) == 1, statements
