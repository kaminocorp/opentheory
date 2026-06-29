"""project invitations: invite an existing account to collaborate

Revision ID: 0010_project_invitations
Revises: 0009_account_email_index
Create Date: 2026-06-29

0.8.7 — the *collaborators + invitation inbox* slice of Project Stewardship & Collaboration
(``docs/executing/project-stewardship-and-collaboration.md`` ask **(C)**). Additive, no data
backfill:

- ``invitation_status`` enum (``PENDING`` / ``ACCEPTED`` / ``DECLINED`` / ``REVOKED``) — the
  lifecycle of a single invitation row.
- ``project_invitations`` — ties an invitee ``Account`` to a ``Project`` with a ``ProjectRole``
  (reuses the ``project_role`` enum from 0007) and an ``invitation_status``. A
  ``UniqueConstraint(project_id, invitee_account_id)`` keeps **one** invitation row per
  (project, invitee): re-inviting a declined/revoked user resets that row to ``PENDING`` rather than
  inserting a second. Declared on the model too, so the test harness's
  ``Base.metadata.create_all`` builds exactly what this migration installs.

Enum-label case: this DB's named enums use the StrEnum **member names** as labels, so the status
labels are uppercase ``'PENDING'`` etc. (consistent with ``project_role``'s ``'OWNER'``/``'ADMIN'``
from 0007).

The ``project_role`` enum already exists (created in 0007), so the ``role`` column references it
with ``create_type=False``; only ``invitation_status`` is created here. Backend code + this
migration ship together.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0010_project_invitations"
down_revision: str | None = "0009_account_email_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INVITATION_STATUS_LABELS = ("PENDING", "ACCEPTED", "DECLINED", "REVOKED")


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    bind = op.get_bind()

    # 1. The invitation-status enum (uppercase StrEnum member labels), created before the table.
    postgresql.ENUM(*_INVITATION_STATUS_LABELS, name="invitation_status").create(
        bind, checkfirst=True
    )

    # 2. The invitations table. FKs inline + unnamed (Postgres names them <table>_<col>_fkey),
    #    matching the baseline idiom. `role` reuses the existing project_role enum (create_type=
    #    False); created_at/updated_at carry no server default (the ORM supplies them, like every
    #    other table).
    op.create_table(
        "project_invitations",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("project_id", _uuid(), nullable=False),
        sa.Column("invitee_account_id", _uuid(), nullable=False),
        sa.Column(
            "role",
            postgresql.ENUM("OWNER", "ADMIN", name="project_role", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                *_INVITATION_STATUS_LABELS, name="invitation_status", create_type=False
            ),
            nullable=False,
        ),
        sa.Column("invited_by_account_id", _uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invitee_account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["invited_by_account_id"], ["accounts.id"], ondelete="SET NULL"
        ),
        # One invitation row per (project, invitee) — explicitly named to match the model.
        sa.UniqueConstraint(
            "project_id", "invitee_account_id", name="uq_project_invitation"
        ),
    )
    # Per-FK lookup indexes (the model declares index=True on both).
    op.create_index(
        "ix_project_invitations_project_id", "project_invitations", ["project_id"]
    )
    op.create_index(
        "ix_project_invitations_invitee_account_id",
        "project_invitations",
        ["invitee_account_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_project_invitations_invitee_account_id", table_name="project_invitations"
    )
    op.drop_index("ix_project_invitations_project_id", table_name="project_invitations")
    op.drop_table("project_invitations")
    postgresql.ENUM(name="invitation_status").drop(op.get_bind(), checkfirst=True)
