"""Per-agent roster caps (0.58.0).

``token_budget_cap`` / ``usd_budget_cap`` on ``project_agent_members`` are
**lifetime** ceilings per roster seat — the design names no period.
Null means no per-agent limit. The shared project daily cap and the
project pot stay as they are; this is an extra refuse-before-model
gate, not a split of the daily hold.

Remaining tokens = cap − billed ``ComputeDebit`` for this
``(project_id, actor_id)`` (``tokens_used > 0``, holds/releases
excluded) − this agent's unmatched remaining-room holds. USD remaining
= cap − billed ``amount`` (holds are amount 0). Callers must load this
under the project-row ``FOR UPDATE`` so two concurrent starts cannot
both pass a nearly-exhausted cap.

FastAPI may import this module. It must not import ``app.harness``.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.compute_debit import ComputeDebit
from app.services.harness_meter import (
    is_daily_cap_adjustment,
    load_today_adjustments,
    pot_tokens_from_available,
    unmatched_holds,
)

REASON_AGENT_TOKEN_CAP = "agent token budget cap exhausted"
REASON_AGENT_USD_CAP = "agent usd budget cap exhausted"


@dataclass(frozen=True)
class AgentCapRoom:
    """Lifetime remaining room for one roster seat. ``None`` cap = unlimited."""

    token_cap: int | None
    usd_cap: Decimal | None
    tokens_billed: int
    amount_billed: Decimal
    tokens_held: int
    token_remaining: int | None
    usd_remaining: Decimal | None

    @property
    def token_reached(self) -> bool:
        return self.token_remaining is not None and self.token_remaining <= 0

    @property
    def usd_reached(self) -> bool:
        return self.usd_remaining is not None and self.usd_remaining <= 0


def refuse_reason(room: AgentCapRoom) -> str | None:
    """Distinct refuse copy when a set cap has no remaining room."""
    if room.usd_reached:
        return REASON_AGENT_USD_CAP
    if room.token_reached:
        return REASON_AGENT_TOKEN_CAP
    return None


def _token_remaining(cap: int | None, billed: int, held: int) -> int | None:
    if cap is None:
        return None
    return max(0, int(cap) - billed - held)


def _usd_remaining(cap: Decimal | None, billed: Decimal) -> Decimal | None:
    if cap is None:
        return None
    leftover = cap - billed
    return leftover if leftover > 0 else Decimal("0")


async def billed_agent_spend(
    db: AsyncSession, project_id: UUID, actor_id: UUID
) -> tuple[int, Decimal]:
    """Lifetime billed spend for this actor on this project. Holds are not spend."""
    result = await db.execute(
        select(ComputeDebit.tokens_used, ComputeDebit.amount, ComputeDebit.notes).where(
            ComputeDebit.project_id == project_id,
            ComputeDebit.actor_id == actor_id,
        )
    )
    tokens = 0
    amount = Decimal("0")
    for tokens_used, row_amount, notes in result:
        if tokens_used <= 0 or is_daily_cap_adjustment(notes):
            continue
        tokens += int(tokens_used)
        amount += Decimal(row_amount)
    return tokens, amount


async def outstanding_hold_tokens(
    db: AsyncSession, project_id: UUID, actor_id: UUID
) -> int:
    """Unmatched remaining-room hold tokens stamped to this actor today."""
    rows = await load_today_adjustments(db, project_id)
    total = 0
    for row in unmatched_holds(rows):
        if getattr(row, "actor_id", None) == actor_id:
            total += max(0, int(row.tokens_used))
    return total


async def load_agent_cap_room(
    db: AsyncSession, project_id: UUID, actor_id: UUID
) -> AgentCapRoom:
    """Roster caps plus billed + outstanding holds. No roster row → no cap."""
    from app.services.agent_roster import get_roster_row

    seat = await get_roster_row(db, project_id, actor_id)
    token_cap = seat.token_budget_cap if seat is not None else None
    usd_cap = seat.usd_budget_cap if seat is not None else None
    billed_tokens, billed_amount = await billed_agent_spend(db, project_id, actor_id)
    held = await outstanding_hold_tokens(db, project_id, actor_id) if token_cap is not None else 0
    return AgentCapRoom(
        token_cap=token_cap,
        usd_cap=usd_cap,
        tokens_billed=billed_tokens,
        amount_billed=billed_amount,
        tokens_held=held,
        token_remaining=_token_remaining(token_cap, billed_tokens, held),
        usd_remaining=_usd_remaining(usd_cap, billed_amount),
    )


def agent_token_room_for_clamp(
    room: AgentCapRoom, *, rate_per_1k: Decimal | None
) -> int | None:
    """Token bound from the set caps. ``None`` when no per-agent token bound applies.

    A USD cap converts at a *known* rate the same way pot room does. An
    unknown rate does not invent a blended price — USD then only refuses
    when already reached.
    """
    token_room = room.token_remaining
    usd_tokens: int | None = None
    if room.usd_remaining is not None and rate_per_1k is not None:
        usd_tokens = pot_tokens_from_available(room.usd_remaining, rate_per_1k)
    if token_room is None:
        return usd_tokens
    if usd_tokens is None:
        return token_room
    return min(token_room, usd_tokens)
