"""Shared harness ``ComputeDebit`` meter (0.49.0).

The session owner in ``app.harness.session`` *writes* remaining-room
holds and spend against today's ``harness_session_turn`` prefix. The
product ops dashboard *reads* the same ledger. This module is the
shared meter so those two paths cannot drift.

FastAPI may import this module. It must not import ``app.harness``.
Nothing here writes. ``create_checkpoint`` is still the only Checkpoint
writer; ``record_compute_debit`` / ``write_daily_cap_adjustment`` stay
on the harness / compute writers.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.compute_debit import ComputeDebit

DAILY_TOKEN_CAP_ENV = "OPENTHEORY_HARNESS_DAILY_TOKEN_CAP"
HOLD_TTL_ENV = "OPENTHEORY_HARNESS_HOLD_TTL_SECONDS"
DEFAULT_DAILY_TOKEN_CAP = 20_000
DEFAULT_HOLD_TTL_SECONDS = 300
SESSION_NOTES = "harness_session_turn"
HOLD_NOTES_MARK = "daily_cap_hold"
RELEASE_NOTES_MARK = "daily_cap_release"
HOLD_ID_MARK = "hold_id="
HOLD_NOTES = f"{SESSION_NOTES}; {HOLD_NOTES_MARK}"
RELEASE_NOTES = f"{SESSION_NOTES}; {RELEASE_NOTES_MARK}"

ProcessIntSource = Literal["default", "process_env", "invalid"]
HarnessRowKind = Literal["spend", "hold", "release"]
BudgetState = Literal["unfunded", "available", "exhausted"]
HoldStatus = Literal["open", "released"]


@dataclass(frozen=True)
class ProcessInt:
    """An integer this API process can see. ``invalid`` means unknown — do not guess."""

    value: int | None
    source: ProcessIntSource


class AdjustmentRow(Protocol):
    """Minimal hold/release row: notes + tokens. ``ComputeDebit`` satisfies this."""

    tokens_used: int
    notes: str | None


class HoldPairRow(Protocol):
    """Hold/release row the dashboard can date. ``ComputeDebit`` satisfies this."""

    tokens_used: int
    notes: str | None
    created_at: datetime


@dataclass(frozen=True)
class PairedHold:
    """One remaining-room hold and the release credit that closed it, if any."""

    hold_id: UUID | None
    status: HoldStatus
    tokens: int
    created_at: datetime
    released_at: datetime | None
    notes: str | None


def utc_day_start(now: datetime | None = None) -> datetime:
    """Inclusive start of the current UTC day (the daily-cap window)."""
    moment = datetime.now(UTC) if now is None else now
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    moment = moment.astimezone(UTC)
    return moment.replace(hour=0, minute=0, second=0, microsecond=0)


def harness_notes_prefix_match(notes: str = SESSION_NOTES):
    """Literal notes prefix. ``_`` / ``%`` in the marker are not LIKE wildcards."""
    return ComputeDebit.notes.startswith(notes, autoescape=True)


def is_daily_cap_adjustment(notes: str | None) -> bool:
    """True for a daily-cap hold or release row, not a billed spend debit."""
    text = notes or ""
    return HOLD_NOTES_MARK in text or RELEASE_NOTES_MARK in text


def hold_notes(hold_id: UUID) -> str:
    """Hold notes: literal ``harness_session_turn`` prefix plus ``hold_id``."""
    return f"{HOLD_NOTES}; {HOLD_ID_MARK}{hold_id}"


def release_notes(hold_id: UUID | None) -> str:
    """Release notes. ``hold_id`` is omitted only for pre-0.48.0 leftover rows."""
    if hold_id is None:
        return RELEASE_NOTES
    return f"{RELEASE_NOTES}; {HOLD_ID_MARK}{hold_id}"


def parse_hold_id(notes: str | None) -> UUID | None:
    """Read ``hold_id=<uuid>`` from a hold or release notes suffix."""
    for part in (notes or "").split(";"):
        token = part.strip()
        if not token.startswith(HOLD_ID_MARK):
            continue
        raw = token[len(HOLD_ID_MARK) :]
        try:
            return UUID(raw)
        except ValueError:
            return None
    return None


def is_hold_stale(
    created_at: datetime,
    *,
    ttl_seconds: int,
    now: datetime | None = None,
) -> bool:
    """True when an unmatched hold is old enough to release.

    ``ttl_seconds < 1`` is fail-closed — never auto-release. A just-taken
    hold must stay so a concurrent authorize cannot treat it as an orphan.
    """
    if ttl_seconds < 1:
        return False
    moment = datetime.now(UTC) if now is None else now
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    created = created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return (moment.astimezone(UTC) - created.astimezone(UTC)).total_seconds() >= ttl_seconds


def unmatched_holds(rows: list[AdjustmentRow]) -> list[AdjustmentRow]:
    """Hold rows that have no matching release on ``rows`` (today's adjustments).

    Identified holds (notes carry ``hold_id``) pair exactly. Pre-0.48.0
    leftover holds without an id pair FIFO against id-less releases so a
    crash leftover from 0.47.0 can still be released.
    """
    released_ids: set[UUID] = set()
    legacy_release_tokens = 0
    identified: list[AdjustmentRow] = []
    legacy: list[AdjustmentRow] = []
    for row in rows:
        text = row.notes or ""
        hold_id = parse_hold_id(text)
        if RELEASE_NOTES_MARK in text:
            if hold_id is not None:
                released_ids.add(hold_id)
            else:
                legacy_release_tokens += row.tokens_used
            continue
        if HOLD_NOTES_MARK not in text:
            continue
        if hold_id is not None:
            identified.append(row)
        else:
            legacy.append(row)

    open_rows = [row for row in identified if parse_hold_id(row.notes) not in released_ids]
    remaining_release = -legacy_release_tokens
    for row in legacy:
        if remaining_release >= row.tokens_used:
            remaining_release -= row.tokens_used
            continue
        open_rows.append(row)
    return open_rows


def classify_harness_row(notes: str | None) -> HarnessRowKind:
    """Spend / hold / release from notes. Unknown suffixes stay ``spend``."""
    text = notes or ""
    if HOLD_NOTES_MARK in text:
        return "hold"
    if RELEASE_NOTES_MARK in text:
        return "release"
    return "spend"


def pair_holds(rows: list[HoldPairRow]) -> list[PairedHold]:
    """Pair today's hold rows with matching release credits.

    Identified ``hold_id`` values pair exactly. Pre-0.48.0 leftover holds
    without an id pair FIFO against id-less releases. Order is hold
    created_at, then hold_id string so the payload is deterministic.
    """
    releases_by_id: dict[UUID, HoldPairRow] = {}
    legacy_releases: list[HoldPairRow] = []
    holds: list[HoldPairRow] = []
    for row in rows:
        text = row.notes or ""
        hold_id = parse_hold_id(text)
        if RELEASE_NOTES_MARK in text:
            if hold_id is not None and hold_id not in releases_by_id:
                releases_by_id[hold_id] = row
            elif hold_id is None:
                legacy_releases.append(row)
            continue
        if HOLD_NOTES_MARK in text:
            holds.append(row)

    paired: list[PairedHold] = []
    legacy_index = 0
    for hold in holds:
        hold_id = parse_hold_id(hold.notes)
        release: HoldPairRow | None = None
        if hold_id is not None:
            release = releases_by_id.get(hold_id)
        elif legacy_index < len(legacy_releases):
            release = legacy_releases[legacy_index]
            legacy_index += 1
        paired.append(
            PairedHold(
                hold_id=hold_id,
                status="released" if release is not None else "open",
                tokens=hold.tokens_used,
                created_at=hold.created_at,
                released_at=release.created_at if release is not None else None,
                notes=hold.notes,
            )
        )
    paired.sort(key=lambda item: (item.created_at, str(item.hold_id or "")))
    return paired


def budget_state(*, funded: object, available: object) -> BudgetState:
    """Unfunded ≠ exhausted. ``funded == 0`` is unfunded even if spend exists."""
    funded_n = funded if isinstance(funded, int | float) else float(funded)
    available_n = available if isinstance(available, int | float) else float(available)
    if funded_n <= 0:
        return "unfunded"
    if available_n <= 0:
        return "exhausted"
    return "available"


def peek_process_int(
    name: str,
    default: int,
    env: Mapping[str, str] | None = None,
) -> ProcessInt:
    """Read an operator int from *this* process. Invalid is unknown, not a guess."""
    lookup = env if env is not None else os.environ
    raw = (lookup.get(name) or "").strip()
    if not raw:
        return ProcessInt(value=default, source="default")
    try:
        value = int(raw)
    except ValueError:
        return ProcessInt(value=None, source="invalid")
    if value < 1:
        return ProcessInt(value=None, source="invalid")
    return ProcessInt(value=value, source="process_env")


def peek_daily_token_cap(env: Mapping[str, str] | None = None) -> ProcessInt:
    return peek_process_int(DAILY_TOKEN_CAP_ENV, DEFAULT_DAILY_TOKEN_CAP, env)


def peek_hold_ttl_seconds(env: Mapping[str, str] | None = None) -> ProcessInt:
    return peek_process_int(HOLD_TTL_ENV, DEFAULT_HOLD_TTL_SECONDS, env)


async def harness_tokens_used_today(
    db: AsyncSession,
    project_id: UUID,
    *,
    now: datetime | None = None,
    notes: str = SESSION_NOTES,
) -> int:
    """Σ tokens_used on today's harness_session_turn ComputeDebit rows.

    The existing ledger is the meter — a process restart does not reset
    this sum. Rows whose notes start with the literal
    ``harness_session_turn`` prefix count (``record_compute_debit`` may
    append a rate-fallback suffix). ``_`` in that marker is not a LIKE
    wildcard. Other project spend (agent-pass debits) does not. Window
    is UTC midnight inclusive through now. Holds and releases count:
    that is the sum ``authorize()`` uses.
    """
    start = utc_day_start(now)
    result = await db.execute(
        select(func.coalesce(func.sum(ComputeDebit.tokens_used), 0)).where(
            ComputeDebit.project_id == project_id,
            ComputeDebit.created_at >= start,
            harness_notes_prefix_match(notes),
        )
    )
    return int(result.scalar_one() or 0)


async def load_today_adjustments(
    db: AsyncSession,
    project_id: UUID,
    *,
    now: datetime | None = None,
    notes: str = SESSION_NOTES,
) -> list[ComputeDebit]:
    """Today's hold / release rows for ``project_id``, oldest first."""
    start = utc_day_start(now)
    result = await db.execute(
        select(ComputeDebit)
        .where(
            ComputeDebit.project_id == project_id,
            ComputeDebit.created_at >= start,
            harness_notes_prefix_match(notes),
        )
        .order_by(ComputeDebit.created_at.asc(), ComputeDebit.id.asc())
    )
    return [row for row in result.scalars().all() if is_daily_cap_adjustment(row.notes)]


async def load_recent_harness_rows(
    db: AsyncSession,
    project_id: UUID,
    *,
    limit: int = 20,
    notes: str = SESSION_NOTES,
) -> list[ComputeDebit]:
    """Newest harness_session_turn rows (spend, hold, release). Read only."""
    capped = max(1, min(limit, 100))
    result = await db.execute(
        select(ComputeDebit)
        .where(
            ComputeDebit.project_id == project_id,
            harness_notes_prefix_match(notes),
        )
        .order_by(ComputeDebit.created_at.desc(), ComputeDebit.id.desc())
        .limit(capped)
    )
    return list(result.scalars().all())
