"""account email index: case-insensitive lookup for invite resolution

Revision ID: 0009_account_email_index
Revises: 0008_account_username
Create Date: 2026-06-29

0.8.4 — post-review hardening on the 0.8.3 ``@username`` slice. ``resolve_account_by_identifier``
(shipped in 0.8.3 as the invite resolver) matches an email **case-insensitively** via
``lower(email)``. This adds a functional index on that expression so the lookup stays off a
sequential scan as ``accounts`` grows.

Additive + **non-unique**: ``email`` is intentionally not uniqueness-enforced
(``docs/executing/project-stewardship-and-collaboration.md`` §7) — an ambiguous email becomes a
``409`` in the invite service, never a DB constraint. Mirrors ``Account.__table_args__`` so the test
harness's ``create_all`` builds exactly this.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009_account_email_index"
down_revision: str | None = "0008_account_username"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_accounts_email_lower", "accounts", [sa.text("lower(email)")], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_accounts_email_lower", table_name="accounts")
