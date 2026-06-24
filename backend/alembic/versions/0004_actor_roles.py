"""actor roles (queryable authorization)

Revision ID: 0004_actor_roles
Revises: 0003_checkpoint_branch_id
Create Date: 2026-06-24

0.6.1 adds verified identity. A single column-level change on ``actors``:

- Add ``roles`` (``ARRAY(String)``, NOT NULL, server default empty array ``'{}'``). The
  server default makes the backfill a no-op — existing actors get ``[]``. An ``internal``
  (Kamino) role gates native funding (0.6.3); the column is the reusable substrate for
  validator/agent permissions later. ``roles`` is a mutable identity attribute (like
  ``branches.status``), not a ledger event, so it is intentionally *not* append-only guarded.

No enum, no new table, no other change.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004_actor_roles"
down_revision: str | None = "0003_checkpoint_branch_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "actors",
        sa.Column(
            "roles",
            postgresql.ARRAY(sa.String()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("actors", "roles")
