from collections.abc import Set as AbstractSet

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.usernames import (
    RESERVED_USERNAMES,
    USERNAME_MAX,
    base_from,
    generate_username_candidates,
)
from app.models.account import Account
from app.schemas.account import AccountCreate

# How many times we retry a username on a unique-constraint race before giving up. The pre-query in
# `generate_unique_username` makes the common case one round-trip; this bounds the (rare) concurrent
# first-login race where two principals pick the same base simultaneously.
USERNAME_INSERT_RETRIES = 6

# Widest numeric suffix the prefix pre-query must keep visible. `with_suffix` truncates a long base
# before appending the digits, so a suffixed candidate (e.g. `aaa…a` -> `aaa…2`) no longer starts
# with the *full* base; we shorten the LIKE prefix by this much so those candidates still match the
# pre-query (covers up to 999999 same-base accounts). The caller's `exclude` set is the hard
# guarantee of forward progress; this just keeps the common case to one round-trip.
_MAX_SUFFIX_WIDTH = 6


async def generate_unique_username(
    db: AsyncSession, base: str, *, exclude: AbstractSet[str] = frozenset()
) -> str:
    """Return a username derived from ``base`` that is **currently** free (and not reserved).

    Pre-queries the handles sharing ``base``'s prefix in one round-trip, then walks
    ``base``, ``base2``, ``base3`` … skipping anything taken, reserved, or in ``exclude``. The
    result is only *advisory* — a concurrent insert can still claim it between this read and the
    caller's write — so the caller's ``INSERT`` (guarded by ``uq_accounts_username``) is the final
    arbiter and retries with the next candidate on collision, passing the just-failed handle in
    ``exclude`` so each retry makes forward progress. Sequential suffixing keeps handles readable.
    """
    # Pre-query the prefix `base` shares with its candidates. We trim the prefix by the max suffix
    # width because `with_suffix` truncates a long base before appending digits — `aaa…a` (30 chars)
    # -> `aaa…2` no longer starts with the full base, so a full-`base` prefix would miss it and the
    # walk could return an already-taken handle (the INSERT then fails identically on every retry,
    # exhausting them). `_` is a LIKE wildcard, so escape it. `username` is lowercase-on-write, so
    # match the column directly — a `func.lower()` wrapper would be a no-op that hides the index.
    prefix = base[: max(1, USERNAME_MAX - _MAX_SUFFIX_WIDTH)]
    like_prefix = prefix.replace("_", r"\_") + "%"
    rows = await db.execute(
        select(Account.username).where(Account.username.like(like_prefix, escape="\\"))
    )
    taken = {row for (row,) in rows} | RESERVED_USERNAMES | set(exclude)
    for candidate in generate_username_candidates(base):
        if candidate not in taken:
            return candidate
    # generate_username_candidates is effectively unbounded, so this is unreachable; kept for type
    # completeness.
    raise RuntimeError("exhausted username candidates")  # pragma: no cover


async def create_account(db: AsyncSession, payload: AccountCreate) -> Account:
    """Dev/test bootstrap (behind ``auth_dev_header_enabled``). Production accounts are
    JIT-provisioned with their primary human Actor on first sign-in (``api/deps.py``); this exists
    only so tests can build an internal funder without seeding (Decision #8).

    Mints a unique ``username`` from the display name / email (0.8.3), retrying on the rare
    unique-constraint race so two bootstraps with the same display name still get distinct handles.
    """
    data = payload.model_dump()
    base = base_from(data.get("email"), data.get("display_name"))
    tried: set[str] = set()
    for _ in range(USERNAME_INSERT_RETRIES):
        username = await generate_unique_username(db, base, exclude=tried)
        account = Account(**data, username=username)
        db.add(account)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            tried.add(username)  # never re-offer the handle that just lost the race
            continue
        await db.refresh(account)
        return account
    raise RuntimeError("could not allocate a unique username")  # pragma: no cover


async def list_accounts(db: AsyncSession) -> list[Account]:
    result = await db.execute(select(Account).order_by(Account.created_at.desc()))
    return list(result.scalars())


async def resolve_account_by_identifier(db: AsyncSession, identifier: str) -> Account | None:
    """Resolve a free-text invite identifier (a ``@username`` **or** an email) to an ``Account``.

    Prerequisite for the 0.8.4 invite flow: an ``@``-bearing identifier matches ``email``
    case-insensitively; otherwise it is treated as a handle (a leading ``@`` is stripped) and
    matched against ``username``. Returns ``None`` when nothing matches.

    Caveat carried from the proposal §7: ``email`` is **not** uniqueness-enforced, so a (rare)
    multi-match returns the most-recently-created account here; the invite service is where an
    ambiguous email becomes a ``409``.
    """
    identifier = identifier.strip()
    if not identifier:
        return None
    if "@" in identifier and not identifier.startswith("@"):
        result = await db.execute(
            select(Account)
            .where(func.lower(Account.email) == identifier.lower())
            .order_by(Account.created_at.desc())
        )
        return result.scalars().first()
    handle = identifier.lstrip("@").lower()
    result = await db.execute(select(Account).where(Account.username == handle))
    return result.scalar_one_or_none()
