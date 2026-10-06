"""lock public PostgREST: forced RLS, no anon/authenticated grants

Revision ID: 0023_lock_public_api_rls
Revises: 0022_agent_actor_identity
Create Date: 2026-10-06

0.58.1 — record the live public-schema lock in the repo. Live is
already ENABLE+FORCE RLS on every public table, with zero grants to
``anon`` / ``authenticated``. This revision is idempotent so a later
``alembic upgrade head`` matches that state.

- ENABLE + FORCE RLS on every ``public`` base table present at apply
  time (``pg_tables`` loop — not a hard-coded list)
- REVOKE ALL tables/sequences + default privileges from anon and
  authenticated when those roles exist
- No policies. Empty forced RLS denies non-bypass roles. The backend
  connects as a table owner (bypassrls); app traffic is unaffected.

The whole revision is **one transaction**. Downgrade reverses
FORCE/ENABLE only and does **not** re-GRANT (that is a deliberate
ops step, not automatic).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.db.rls_lock import (
    LOCK_PUBLIC_TABLES_SQL,
    REVOKE_POSTGREST_GRANTS_SQL,
    UNLOCK_PUBLIC_TABLES_SQL,
)

revision: str = "0023_lock_public_api_rls"
down_revision: str | None = "0022_agent_actor_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(sa.text(LOCK_PUBLIC_TABLES_SQL))
    op.execute(sa.text(REVOKE_POSTGREST_GRANTS_SQL))


def downgrade() -> None:
    # Re-GRANT to anon/authenticated is a deliberate ops step, not automatic.
    op.execute(sa.text(UNLOCK_PUBLIC_TABLES_SQL))
