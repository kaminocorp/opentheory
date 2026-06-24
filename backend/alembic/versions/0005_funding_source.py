"""funding source discriminator (native vs stripe)

Revision ID: 0005_funding_source
Revises: 0004_actor_roles
Create Date: 2026-06-24

0.6.3 activates the funding write path. A new named enum + one column on
``funding_allocations``:

- Create the ``funding_source`` PG enum with labels ``NATIVE`` / ``STRIPE`` (the StrEnum
  *member names*, matching how the ORM emits them — consistent with ``funding_kind`` /
  ``funding_status`` in the baseline).
- Add ``funding_allocations.source`` (NOT NULL). Funding had no write path before, so the
  table is empty in practice; we still add the column with a temporary ``server_default
  'NATIVE'`` to backfill any pre-existing rows, then drop the default so the column matches
  the ORM (no server default) and ``alembic check`` stays clean.

No other table changes. ``FundingAllocation`` remains append-only.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005_funding_source"
down_revision: str | None = "0004_actor_roles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Labels are the StrEnum member NAMES (SQLAlchemy's default Enum labels), as in the baseline.
_SOURCE_LABELS = ("NATIVE", "STRIPE")


def upgrade() -> None:
    funding_source = postgresql.ENUM(*_SOURCE_LABELS, name="funding_source")
    funding_source.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "funding_allocations",
        sa.Column(
            "source",
            postgresql.ENUM(*_SOURCE_LABELS, name="funding_source", create_type=False),
            nullable=False,
            server_default="NATIVE",
        ),
    )
    # Drop the backfill default so the column matches the ORM definition (no server default).
    op.alter_column("funding_allocations", "source", server_default=None)


def downgrade() -> None:
    op.drop_column("funding_allocations", "source")
    postgresql.ENUM(*_SOURCE_LABELS, name="funding_source").drop(op.get_bind(), checkfirst=True)
