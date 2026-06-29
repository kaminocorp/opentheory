"""project stewardship: background + project membership/authorization

Revision ID: 0007_project_stewardship
Revises: 0006_accounts
Create Date: 2026-06-29

0.8.1 — the opening, *ownership + self-edit* slice of Project Stewardship & Collaboration
(``docs/executing/project-stewardship-and-collaboration.md``). Additive, no data backfill:

- ``projects.background`` ``TEXT`` ``NULL`` — the deep, optional long-form briefing (Markdown
  serialized to plaintext TEXT, see the proposal §4.7).
- ``project_role`` enum (``OWNER`` / ``ADMIN``) — the platform's first *project-level*
  authorization vocabulary, kept structurally separate from the funder/contributor/validator
  credit roles.
- ``project_members`` — ties an ``Account`` (the principal, 0.7.0) to a ``Project`` with a role.
  A ``UniqueConstraint(project_id, account_id)`` allows one membership per principal; a **partial
  unique index** ``uq_project_one_owner`` enforces at most one ``OWNER`` per project. Both are
  declared on the model too, so the test harness's ``Base.metadata.create_all`` builds exactly what
  this migration installs (the ``uq_actors_one_human_per_account`` discipline).

**No ownership backfill** (Decision): existing projects (e.g. "Pythagoras Theorem") get their owner
``project_members`` row added **by hand in Supabase** — until then they are ownerless and
``ensure_can_manage`` ``403``s on them. New projects always get an owner on create (services/
projects.py). Backend code and this migration ship together.

Enum-label case: this DB's named enums use the StrEnum **member names** as labels, so the role
labels are uppercase ``'OWNER'`` / ``'ADMIN'`` and the partial-index predicate is
``role = 'OWNER'`` — lowercase would error with ``invalid input value for enum project_role``.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0007_project_stewardship"
down_revision: str | None = "0006_accounts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PROJECT_ROLE_LABELS = ("OWNER", "ADMIN")


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    bind = op.get_bind()

    # 1. The deep long-form briefing (additive, nullable — no backfill).
    op.add_column("projects", sa.Column("background", sa.Text(), nullable=True))

    # 2. The project-role enum (uppercase StrEnum member labels), created before the table uses it.
    postgresql.ENUM(*_PROJECT_ROLE_LABELS, name="project_role").create(bind, checkfirst=True)

    # 3. The membership table. FKs inline + unnamed (Postgres names them <table>_<col>_fkey),
    #    matching the baseline idiom so autogenerate diffs stay empty. created_at/updated_at carry
    #    no server default (the ORM supplies them, like every other table).
    op.create_table(
        "project_members",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("project_id", _uuid(), nullable=False),
        sa.Column("account_id", _uuid(), nullable=False),
        sa.Column(
            "role",
            postgresql.ENUM(*_PROJECT_ROLE_LABELS, name="project_role", create_type=False),
            nullable=False,
        ),
        sa.Column("invited_by_account_id", _uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["invited_by_account_id"], ["accounts.id"], ondelete="SET NULL"
        ),
        # One membership per (project, account) — explicitly named to match the model.
        sa.UniqueConstraint("project_id", "account_id", name="uq_project_member"),
    )
    # Per-FK lookup indexes (the model declares index=True on both).
    op.create_index("ix_project_members_project_id", "project_members", ["project_id"])
    op.create_index("ix_project_members_account_id", "project_members", ["account_id"])
    # At most one OWNER per project (mirrors the model's __table_args__ index 1:1).
    op.create_index(
        "uq_project_one_owner",
        "project_members",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text("role = 'OWNER'"),
    )


def downgrade() -> None:
    op.drop_index("uq_project_one_owner", table_name="project_members")
    op.drop_index("ix_project_members_account_id", table_name="project_members")
    op.drop_index("ix_project_members_project_id", table_name="project_members")
    op.drop_table("project_members")
    postgresql.ENUM(name="project_role").drop(op.get_bind(), checkfirst=True)
    op.drop_column("projects", "background")
