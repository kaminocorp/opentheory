"""Perpetual ops dashboard — derived read over the compute ledger (0.49.0 / 0.50.0).

``GET /projects/{id}/ops``. Always-on. Mints nothing. Does not import
``app.harness``. The daily-cap numbers are the same meter
``HarnessSession.authorize()`` writes: today's ``ComputeDebit`` rows
whose notes start with the literal ``harness_session_turn`` prefix,
holds included, paired by ``hold_id``.

Unknown stays unknown:
- A refused start writes nothing, so refusals cannot be listed.
- Whether a separate Fly gateway / MCP child is running is not visible
  to this API process.
- An invalid ``OPENTHEORY_HARNESS_DAILY_TOKEN_CAP`` (or hold TTL) on
  *this* process is not replaced with the default.
- The campaign child may override those env vars independently; that
  override is unknown here and is labeled as such.
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.actor import Actor
from app.models.compute_debit import ComputeDebit
from app.models.project import Project
from app.schemas.ops import (
    OpsActorSpendRead,
    OpsBudgetRead,
    OpsDailyCapRead,
    OpsEnablementRead,
    OpsHoldRead,
    OpsLastTurnRead,
    OpsLoopRead,
    OpsRefusalsRead,
    OpsTurnRead,
    OpsUnknownProcessRead,
    ProjectOpsRead,
)
from app.services import funding as funding_service
from app.services.harness_meter import (
    DAILY_TOKEN_CAP_ENV,
    DEFAULT_DAILY_TOKEN_CAP,
    HOLD_TTL_ENV,
    SESSION_NOTES,
    budget_state,
    classify_harness_row,
    harness_notes_prefix_match,
    harness_tokens_used_today,
    is_daily_cap_adjustment,
    is_hold_stale,
    load_recent_harness_rows,
    load_today_adjustments,
    pair_holds,
    parse_clamp,
    parse_hold_id,
    parse_overshoot,
    parse_pot_room,
    parse_price_known,
    peek_daily_token_cap,
    peek_hold_ttl_seconds,
    utc_day_start,
)

RECENT_TURNS_LIMIT = 20

_BUDGET_NOTES = {
    "unfunded": (
        "No settled funding. Unfunded is not exhausted — a funded pot "
        "at available ≤ 0 is the exhausted state."
    ),
    "available": "Settled funding remains after spent and reserved.",
    "exhausted": "Funded and available ≤ 0. Unfunded is a different state.",
}

_REFUSALS = OpsRefusalsRead(
    recorded=False,
    note=(
        "A refused start writes nothing (TurnRefused → no ComputeDebit, "
        "no checkpoint). The ledger cannot list refusals."
    ),
)

_GATEWAY_NOTE = (
    "This API process does not import or mount the OpenRouter gateway. "
    "Whether a separate Fly / host process is running is unknown."
)
_MCP_NOTE = (
    "This API process does not run the MCP child. Whether a separate "
    "process is running is unknown."
)
_CHILD_OVERRIDE_NOTE = (
    f"Cap and TTL are what this API process sees ({DAILY_TOKEN_CAP_ENV} / "
    f"{HOLD_TTL_ENV}). The campaign child may set those independently; "
    "that override is unknown here."
)


def _last_turn_note(
    *,
    clamp: int | None,
    overshoot: int | None,
    price_known: bool | None,
    pot_room: int | None = None,
) -> str:
    if clamp is None:
        return (
            "Newest billed harness spend. No clamp was recorded on this row "
            "(pre-0.50.0, or a write that did not carry the mark)."
        )
    if price_known is False:
        room = "daily room; price unknown — pot room was not used"
    elif pot_room is None:
        room = "daily room; pot room was not applied"
    else:
        room = "min of daily room and pot room"
    if overshoot and overshoot > 0:
        return (
            f"Clamped to {clamp} tokens ({room}). "
            f"Provider reported more (overshoot {overshoot})."
        )
    return f"Clamped to {clamp} tokens ({room}). Provider report fit the clamp."


def _last_turn_read(turn: OpsTurnRead) -> OpsLastTurnRead:
    return OpsLastTurnRead(
        tokens_used=turn.tokens_used,
        clamp=turn.clamp,
        overshoot=turn.overshoot,
        price_known=turn.price_known,
        pot_room=turn.pot_room,
        note=_last_turn_note(
            clamp=turn.clamp,
            overshoot=turn.overshoot,
            price_known=turn.price_known,
            pot_room=turn.pot_room,
        ),
        actor_id=turn.actor_id,
        actor_display_name=turn.actor_display_name,
        actor_type=turn.actor_type,
    )


async def _actor_labels(
    db: AsyncSession, actor_ids: set[UUID]
) -> dict[UUID, Actor]:
    if not actor_ids:
        return {}
    rows = await db.execute(select(Actor).where(Actor.id.in_(actor_ids)))
    return {row.id: row for row in rows.scalars()}


async def _spend_by_agent(
    db: AsyncSession, project_id: UUID, labels: dict[UUID, Actor]
) -> list[OpsActorSpendRead]:
    """Billed harness spend grouped by ``actor_id``. Unknown stays unknown."""
    result = await db.execute(
        select(
            ComputeDebit.actor_id,
            ComputeDebit.tokens_used,
            ComputeDebit.amount,
            ComputeDebit.notes,
        ).where(
            ComputeDebit.project_id == project_id,
            harness_notes_prefix_match(),
        )
    )
    grouped: dict[UUID | None, tuple[int, Decimal, int]] = {}
    for actor_id, tokens_used, amount, notes in result:
        if tokens_used <= 0 or is_daily_cap_adjustment(notes):
            continue
        used, spent, count = grouped.get(actor_id, (0, Decimal("0"), 0))
        grouped[actor_id] = (used + int(tokens_used), spent + Decimal(amount), count + 1)
    out: list[OpsActorSpendRead] = []
    for actor_id, (tokens_used, amount, turn_count) in grouped.items():
        actor = labels.get(actor_id) if actor_id is not None else None
        out.append(
            OpsActorSpendRead(
                actor_id=actor_id,
                actor_display_name=actor.display_name if actor is not None else None,
                actor_type=actor.type if actor is not None else None,
                tokens_used=tokens_used,
                amount=amount,
                turn_count=turn_count,
            )
        )
    out.sort(
        key=lambda row: (
            -(row.tokens_used),
            str(row.actor_id) if row.actor_id is not None else "",
        )
    )
    return out


def _cap_note(source: str) -> str:
    if source == "invalid":
        return (
            f"{DAILY_TOKEN_CAP_ENV} is set on this process but is not a "
            f"positive integer. Remaining and exhausted are unknown. "
            f"{_CHILD_OVERRIDE_NOTE}"
        )
    if source == "process_env":
        return (
            f"Cap from {DAILY_TOKEN_CAP_ENV} on this API process. "
            f"{_CHILD_OVERRIDE_NOTE}"
        )
    return (
        f"Documented default ({DEFAULT_DAILY_TOKEN_CAP} tokens / UTC day); "
        f"{DAILY_TOKEN_CAP_ENV} is unset on this API process. "
        f"{_CHILD_OVERRIDE_NOTE}"
    )


async def project_ops(
    db: AsyncSession,
    project_id: UUID,
    *,
    now: datetime | None = None,
) -> ProjectOpsRead:
    """Derive the operator snapshot. Never writes."""
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    moment = datetime.now(UTC) if now is None else now
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    moment = moment.astimezone(UTC)

    budget = await funding_service.project_budget(db, project_id)
    state = budget_state(funded=budget.funded, available=budget.available)

    cap = peek_daily_token_cap()
    ttl = peek_hold_ttl_seconds()
    used = await harness_tokens_used_today(db, project_id, now=moment)
    remaining: int | None
    exhausted: bool | None
    if cap.value is None:
        remaining = None
        exhausted = None
    else:
        remaining = max(0, cap.value - used)
        exhausted = used >= cap.value

    adjustments = await load_today_adjustments(db, project_id, now=moment)
    holds = [
        OpsHoldRead(
            hold_id=item.hold_id,
            status=item.status,
            tokens=item.tokens,
            created_at=item.created_at,
            released_at=item.released_at,
            stale=(
                None
                if item.status != "open" or ttl.value is None
                else is_hold_stale(item.created_at, ttl_seconds=ttl.value, now=moment)
            ),
            note=(
                "Pre-0.48.0 leftover hold (no hold_id)."
                if item.hold_id is None
                else None
            ),
        )
        for item in pair_holds(adjustments)
    ]

    recent_rows = await load_recent_harness_rows(
        db, project_id, limit=RECENT_TURNS_LIMIT
    )
    label_ids = {row.actor_id for row in recent_rows if row.actor_id is not None}
    spend_ids_result = await db.execute(
        select(ComputeDebit.actor_id).where(
            ComputeDebit.project_id == project_id,
            harness_notes_prefix_match(),
            ComputeDebit.actor_id.is_not(None),
        )
    )
    label_ids.update(aid for (aid,) in spend_ids_result if aid is not None)
    labels = await _actor_labels(db, label_ids)
    recent = []
    for row in recent_rows:
        actor = labels.get(row.actor_id) if row.actor_id is not None else None
        recent.append(
            OpsTurnRead(
                id=row.id,
                created_at=row.created_at,
                tokens_used=row.tokens_used,
                amount=Decimal(row.amount),
                notes=row.notes,
                kind=classify_harness_row(row.notes),
                hold_id=parse_hold_id(row.notes),
                clamp=parse_clamp(row.notes),
                overshoot=parse_overshoot(row.notes),
                price_known=parse_price_known(row.notes),
                pot_room=parse_pot_room(row.notes),
                actor_id=row.actor_id,
                actor_display_name=actor.display_name if actor is not None else None,
                actor_type=actor.type if actor is not None else None,
            )
        )
    last_spend = next((row for row in recent if row.kind == "spend"), None)
    last_turn = _last_turn_read(last_spend) if last_spend is not None else None
    spend_by_agent = await _spend_by_agent(db, project_id, labels)

    return ProjectOpsRead(
        project_id=project_id,
        as_of=moment,
        notes_prefix=SESSION_NOTES,
        budget=OpsBudgetRead(
            snapshot=budget,
            state=state,
            note=_BUDGET_NOTES[state],
        ),
        daily_cap=OpsDailyCapRead(
            utc_day=utc_day_start(moment).date().isoformat(),
            cap=cap.value,
            cap_source=cap.source,
            tokens_used_today=used,
            remaining=remaining,
            exhausted=exhausted,
            hold_ttl_seconds=ttl.value,
            hold_ttl_source=ttl.source,
            note=_cap_note(cap.source),
        ),
        holds=holds,
        recent_turns=recent,
        last_turn=last_turn,
        spend_by_agent=spend_by_agent,
        refusals=_REFUSALS,
        enablement=OpsEnablementRead(
            loop=OpsLoopRead(enabled=settings.agent_loop_enabled),
            gateway=OpsUnknownProcessRead(note=_GATEWAY_NOTE),
            mcp_child=OpsUnknownProcessRead(note=_MCP_NOTE),
        ),
    )
