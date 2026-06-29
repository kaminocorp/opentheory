"""Username (public ``@handle``) normalization helpers (0.8.3).

Pure, **DB-free** string utilities for the account ``@username`` introduced in 0.8.3 — the unique,
public, *renameable* handle on the **principal** (``Account``), distinct from the free-form
non-unique ``display_name`` and the private ``email``. Consumed by:

- ``api/deps.py::_resolve_or_provision`` — auto-generate a handle on first sign-in;
- ``services/account.py`` — the dev/test bootstrap (``POST /accounts``) and the DB-side
  collision-resolving generator (``generate_unique_username``);
- ``schemas/account.py::AccountUpdate`` — validate a user-chosen rename (``PATCH /me``).

The handle is stored **lowercased**; case-insensitive uniqueness then falls out of
lowercase-on-write (no ``citext`` needed). Accepted shape is X/Instagram-style:
``^[a-z0-9_]{3,30}$``.

> The ``0008_account_username`` migration re-inlines an equivalent slugifier rather than importing
> this module — a migration must stay *frozen* (independent of code that may change), the same
> reason ``0006`` used only raw SQL. Keep the two in rough sync, but they need not be identical:
> the migration only has to mint *valid, unique* handles at backfill time.
"""

import re
from collections.abc import Iterator

USERNAME_MIN = 3
USERNAME_MAX = 30

# The canonical shape, also enforced by ``AccountUpdate``. Requires lowercase, so callers lowercase
# *before* matching. Anchored with ``\Z`` (not ``$``): in Python ``$`` also matches *before* a
# trailing newline, so ``"foobar\n"`` would slip through ``.match`` — ``\Z`` matches only the true
# end of string (and aligns with JS ``RegExp`` semantics in the frontend mirror).
USERNAME_PATTERN = re.compile(r"^[a-z0-9_]{3,30}\Z")

# Handles we never auto-generate or accept on rename — they collide with routes / privileged
# identities and would be confusing or misleading as a public ``@handle``. (Note: ``"user"`` is
# deliberately *not* reserved — it is ``base_from``'s last-resort base.)
RESERVED_USERNAMES = frozenset(
    {
        "me",
        "admin",
        "administrator",
        "system",
        "accounts",
        "account",
        "api",
        "anonymous",
        "owner",
        "support",
        "root",
        "null",
        "undefined",
    }
)

_NON_ALLOWED = re.compile(r"[^a-z0-9_]+")
_UNDERSCORE_RUN = re.compile(r"_+")


def normalize(raw: str | None) -> str:
    """Coerce arbitrary text into a valid username *body* (``^[a-z0-9_]{3,30}$``).

    Lowercases; replaces every run of disallowed characters with a single ``_``; collapses
    repeated underscores; trims leading/trailing ``_``; pads anything shorter than the 3-char
    minimum (with ``0``); truncates to 30. Pure + deterministic — **no** randomness and **no**
    reserved-name logic — so it is trivially unit-testable. Uniqueness and reserved-name avoidance
    are layered on top by ``generate_unique_username`` (DB) and the schema validator.
    """
    s = (raw or "").strip().lower()
    s = _NON_ALLOWED.sub("_", s)
    s = _UNDERSCORE_RUN.sub("_", s).strip("_")
    if not s:
        s = "user"
    if len(s) < USERNAME_MIN:
        s = s.ljust(USERNAME_MIN, "0")
    return s[:USERNAME_MAX]


def base_from(email: str | None, display_name: str | None) -> str:
    """Pick a normalized handle *base* for a new account, preferring the email local-part.

    Order: email local-part (stable, usually distinctive) → ``display_name`` → ``"user"``. The
    result is always valid **and non-reserved**: if a preferred source normalizes to a reserved
    word we fall through to the next, so the generator only ever has to suffix for *uniqueness*,
    never to dodge a reserved collision.
    """
    candidates = (
        normalize(email.split("@", 1)[0]) if email and "@" in email else None,
        normalize(display_name) if display_name else None,
    )
    for candidate in candidates:
        if candidate and candidate not in RESERVED_USERNAMES:
            return candidate
    return "user"


def with_suffix(base: str, suffix: str) -> str:
    """Append ``suffix`` to ``base``, truncating ``base`` so the total stays within 30 chars."""
    trimmed = base[: max(1, USERNAME_MAX - len(suffix))]
    return f"{trimmed}{suffix}"


def is_valid_username(value: str) -> bool:
    """True iff ``value`` matches the handle pattern and is not reserved (expects lowercase)."""
    return bool(USERNAME_PATTERN.match(value)) and value not in RESERVED_USERNAMES


def generate_username_candidates(base: str) -> Iterator[str]:
    """Yield handle candidates for ``base``: the bare base, then ``base2``, ``base3`` … forever.

    The DB-side generator consumes this lazily, returning the first candidate not already taken or
    reserved. Suffixing is sequential (readable handles), and ``with_suffix`` keeps each candidate
    within the 30-char limit. Unbounded by design — the caller stops at the first free one.
    """
    yield base
    n = 2
    while True:
        yield with_suffix(base, str(n))
        n += 1
