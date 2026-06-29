"""account @username: a unique public handle on the principal

Revision ID: 0008_account_username
Revises: 0007_project_stewardship
Create Date: 2026-06-29

0.8.3 — the *account ``@username``* slice of Project Stewardship & Collaboration
(``docs/executing/project-stewardship-and-collaboration.md`` §4.2). Adds a unique, public,
renameable handle on the **principal** (``Account``), distinct from the free-form non-unique
``display_name`` and the private ``email``. It is the prerequisite for inviting an existing user
by handle (0.8.4).

**Hand-authored backfill** (like ``0006``): the column is born ``NULL``, every existing account is
assigned a unique handle, then the column is made ``UNIQUE`` + ``NOT NULL``. The slugify/dedupe
logic is **re-inlined here** rather than imported from ``app.core.usernames`` — a migration must
stay *frozen* (a future change to the app helper must not retroactively alter what this migration
does on a fresh DB). It only has to mint *valid, unique* handles at backfill time; it need not
match the app byte-for-byte.

**Ships with the provisioning change** (``api/deps.py``, ``services/account.py``): once ``username``
is ``NOT NULL``, code that can't populate it would fail the next sign-in / account bootstrap, so the
backend code and this migration deploy together.

Empty-DB note: today's live ``accounts`` table is tiny, so the backfill touches a handful of rows;
it is written to be correct for any row count and the round-trip is proven on a throwaway DB.
"""

import re
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008_account_username"
down_revision: str | None = "0007_project_stewardship"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# --- Frozen slugifier (a snapshot of app/core/usernames.py at 0.8.3; do NOT import the app) ------

_USERNAME_MIN = 3
_USERNAME_MAX = 30
_RESERVED = {
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
_NON_ALLOWED = re.compile(r"[^a-z0-9_]+")
_UNDERSCORE_RUN = re.compile(r"_+")


def _normalize(raw: str | None) -> str:
    s = (raw or "").strip().lower()
    s = _NON_ALLOWED.sub("_", s)
    s = _UNDERSCORE_RUN.sub("_", s).strip("_")
    if not s:
        s = "user"
    if len(s) < _USERNAME_MIN:
        s = s.ljust(_USERNAME_MIN, "0")
    return s[:_USERNAME_MAX]


def _base(email: str | None, display_name: str | None) -> str:
    candidates = (
        _normalize(email.split("@", 1)[0]) if email and "@" in email else None,
        _normalize(display_name) if display_name else None,
    )
    for candidate in candidates:
        if candidate and candidate not in _RESERVED:
            return candidate
    return "user"


def _dedupe(base: str, taken: set[str]) -> str:
    if base not in taken:
        return base
    n = 2
    while True:
        suffix = str(n)
        candidate = base[: max(1, _USERNAME_MAX - len(suffix))] + suffix
        if candidate not in taken:
            return candidate
        n += 1


def upgrade() -> None:
    # 1. Born nullable so the add never fails on existing rows.
    op.add_column("accounts", sa.Column("username", sa.String(length=30), nullable=True))

    # 2. Backfill a unique handle per existing account. Deterministic order so a re-run on the same
    #    data produces the same handles; the `taken` set carries the reserved words + every handle
    #    minted so far, so collisions suffix to base2/base3/...
    bind = op.get_bind()
    rows = (
        bind.execute(
            sa.text("SELECT id, email, display_name FROM accounts ORDER BY created_at, id")
        )
        .mappings()
        .all()
    )
    taken: set[str] = set(_RESERVED)
    for row in rows:
        handle = _dedupe(_base(row["email"], row["display_name"]), taken)
        taken.add(handle)
        bind.execute(
            sa.text("UPDATE accounts SET username = :u WHERE id = :id"),
            {"u": handle, "id": row["id"]},
        )

    # 3. Now that every row is populated, enforce uniqueness + NOT NULL. The constraint is named to
    #    match the model's `__table_args__` (`uq_accounts_username`), so `create_all` in tests
    #    builds exactly this.
    op.create_unique_constraint("uq_accounts_username", "accounts", ["username"])
    op.alter_column("accounts", "username", nullable=False)


def downgrade() -> None:
    op.drop_constraint("uq_accounts_username", "accounts", type_="unique")
    op.drop_column("accounts", "username")
