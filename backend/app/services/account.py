from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.usernames import (
    RESERVED_USERNAMES,
    base_from,
    generate_username_candidates,
)
from app.models.account import Account
from app.schemas.account import AccountCreate

# How many times we retry a username on a unique-constraint race before giving up. The pre-query in
# `generate_unique_username` makes the common case one round-trip; this bounds the (rare) concurrent
# first-login race where two principals pick the same base simultaneously.
USERNAME_INSERT_RETRIES = 6


async def generate_unique_username(db: AsyncSession, base: str) -> str:
    """Return a username derived from ``base`` that is **currently** free (and not reserved).

    Pre-queries the handles sharing ``base``'s prefix in one round-trip, then walks
    ``base``, ``base2``, ``base3`` … skipping anything taken or reserved. The result is only
    *advisory* — a concurrent insert can still claim it between this read and the caller's write —
    so the caller's ``INSERT`` (guarded by ``uq_accounts_username``) is the final arbiter and
    retries with the next candidate on collision. Sequential suffixing (not random) keeps generated
    handles readable.
    """
    # `base` is normalized to [a-z0-9_], so `_` (a LIKE wildcard) must be escaped or the prefix
    # over-matches; over-matching is harmless (it only ever adds *real* taken handles to the set),
    # but escaping keeps the query honest. `username` is lowercase-on-write, so we match the column
    # directly — wrapping it in `func.lower()` would be a no-op that only hides the column from any
    # index the planner might use.
    like_prefix = base.replace("_", r"\_") + "%"
    rows = await db.execute(
        select(Account.username).where(Account.username.like(like_prefix, escape="\\"))
    )
    taken = {row for (row,) in rows} | RESERVED_USERNAMES
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
    for _ in range(USERNAME_INSERT_RETRIES):
        username = await generate_unique_username(db, base)
        account = Account(**data, username=username)
        db.add(account)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
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
