"""compute_debits: live OpenRouter rate snapshot columns

Revision ID: 0020_compute_debit_live_rates
Revises: 0019_concurrent_subpasses
Create Date: 2026-09-25

0.28.0 — live OpenRouter price metering. Additive, no data rewrite.
Rebased after shipped ``0.27.0`` (``0019_concurrent_subpasses``).

- ``compute_debit_rate_source`` enum (``OPENROUTER_LIVE`` / ``CATALOG_OVERRIDE`` /
  ``BLENDED_FALLBACK``) — where the rate on a debit came from. Existing rows
  backfill to ``BLENDED_FALLBACK`` (they were billed at the 0.19.0 blended
  default). A fallback is never presented as a live price.
- ``prompt_tokens`` / ``completion_tokens`` — the provider split when known.
- ``prompt_rate_per_1k`` / ``completion_rate_per_1k`` — live rate snapshot.
- ``rate_source`` — required; server default ``BLENDED_FALLBACK`` so pre-0.28.0
  insert paths and existing rows stay valid.

``rate_per_1k`` and ``amount`` stay; when live split billing is used,
``rate_per_1k`` is the realized blend (amount × 1000 / tokens).

Enum-label case: this DB's named enums use the StrEnum **member names** as
labels. Additive and non-destructive; ``downgrade`` drops the new columns and
the enum.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0020_compute_debit_live_rates"
down_revision: str | None = "0019_concurrent_subpasses"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RATE_SOURCE_LABELS = ("OPENROUTER_LIVE", "CATALOG_OVERRIDE", "BLENDED_FALLBACK")


def upgrade() -> None:
    bind = op.get_bind()

    postgresql.ENUM(*_RATE_SOURCE_LABELS, name="compute_debit_rate_source").create(
        bind, checkfirst=True
    )

    op.add_column("compute_debits", sa.Column("prompt_tokens", sa.Integer(), nullable=True))
    op.add_column("compute_debits", sa.Column("completion_tokens", sa.Integer(), nullable=True))
    op.add_column(
        "compute_debits",
        sa.Column("prompt_rate_per_1k", sa.Numeric(12, 6), nullable=True),
    )
    op.add_column(
        "compute_debits",
        sa.Column("completion_rate_per_1k", sa.Numeric(12, 6), nullable=True),
    )
    op.add_column(
        "compute_debits",
        sa.Column(
            "rate_source",
            postgresql.ENUM(
                *_RATE_SOURCE_LABELS,
                name="compute_debit_rate_source",
                create_type=False,
            ),
            nullable=False,
            server_default="BLENDED_FALLBACK",
        ),
    )


def downgrade() -> None:
    op.drop_column("compute_debits", "rate_source")
    op.drop_column("compute_debits", "completion_rate_per_1k")
    op.drop_column("compute_debits", "prompt_rate_per_1k")
    op.drop_column("compute_debits", "completion_tokens")
    op.drop_column("compute_debits", "prompt_tokens")
    postgresql.ENUM(name="compute_debit_rate_source").drop(op.get_bind(), checkfirst=True)
