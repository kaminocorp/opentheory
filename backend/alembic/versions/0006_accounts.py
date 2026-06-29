"""accounts: the auth principal that owns actors (Account-owns-Actor)

Revision ID: 0006_accounts
Revises: 0005_funding_source
Create Date: 2026-06-28

0.7.0 opening slice. Introduces ``accounts`` (the authentication *principal*, one per Supabase
``auth.users`` login) that **owns** one or more ``actors``, and relocates three principal-level
concerns onto it:

- ``external_id`` (the IdP ``sub``) moves from ``actors`` to ``accounts`` — the unique key auth
  resolves on (Decision #3);
- ``roles`` moves from ``actors`` to ``accounts`` — authorization describes the principal, not a
  single action identity (Decision #4);
- funding attribution moves from ``funding_allocations.actor_id`` to ``account_id`` — money is the
  principal's (Decision #5). The ``fund`` *Contribution* stays actor-attributed (the act vs. the
  money), so research provenance is untouched.

Research provenance FKs (``checkpoints.author_id``, ``contributions.actor_id``,
``validations.actor_id``) are deliberately unchanged — the ledger still attributes actions to an
``Actor``.

**Destructive + hand-authored.** The backfills are not autogeneratable, so this is written by hand
(autogenerate only cross-checks the DDL). The data move runs *between* the additive DDL and the
column drops, so the migration must ship together with the Phases 1–5 backend code — old code that
reads ``actors.roles`` breaks the instant the column is gone (see the implementation plan's
sequencing).

Enum-label case (the Phase 0 trap): this DB's named enums use the StrEnum **member names** as
labels, so the actor type is ``'HUMAN'`` (uppercase), *not* ``'human'`` — every raw-SQL predicate
below uses the uppercase label. Lowercase ``type='human'`` errors here with
``invalid input value for enum actor_type``.

Empty-DB note: as of the Phase 0 audit the live ``actors`` / ``funding_allocations`` tables are
empty, so the backfills move **0 rows** on today's data. They are written to be correct for any
rows that appear before cutover, and the round-trip is proven on a throwaway DB regardless of row
count (Phase 9). ``gen_random_uuid()`` is core in Postgres 13+ (Supabase is 15), so no extension
is required to mint the server-side account pks.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006_accounts"
down_revision: str | None = "0005_funding_source"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    # 1. The new principal table. Timestamps/pk carry no server default — the ORM supplies them
    #    (IdMixin uuid4 / TimestampMixin datetime.now), matching every other table in the baseline.
    #    `roles` keeps the `'{}'` server default so it mirrors the model and `alembic check` stays
    #    clean. `external_id` is unique + nullable (a future org/service account may have no `sub`).
    op.create_table(
        "accounts",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column(
            "roles",
            postgresql.ARRAY(sa.String()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("account_metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        # Unnamed to match the model's column-level unique=True (Postgres names it
        # accounts_external_id_key), keeping autogenerate diffs empty — the actors idiom.
        sa.UniqueConstraint("external_id"),
    )

    # 2. The owning-principal link on actors. ON DELETE SET NULL keeps the (immutable, ledger-
    #    referenced) actor row if its account is ever removed. No plain index: the partial unique
    #    index (step 6) is the only index on account_id, matching the model.
    op.add_column("actors", sa.Column("account_id", _uuid(), nullable=True))
    op.create_foreign_key(
        "fk_actors_account_id_accounts",
        "actors",
        "accounts",
        ["account_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 3. Backfill: one account per existing human actor, then link each human actor to it.
    #    `gen_random_uuid()` mints the pk server-side (the ORM's Python uuid4 default is unavailable
    #    in raw SQL); email is promoted out of actor_metadata; created_at/updated_at carry over so
    #    the account inherits the actor's provenance timestamps. Uppercase 'HUMAN' (enum label).
    op.execute(
        sa.text(
            """
            INSERT INTO accounts (
                id, external_id, display_name, email, roles, account_metadata,
                created_at, updated_at
            )
            SELECT gen_random_uuid(), a.external_id, a.display_name,
                   a.actor_metadata->>'email', a.roles, '{}'::json,
                   a.created_at, a.updated_at
            FROM actors a
            WHERE a.type = 'HUMAN' AND a.external_id IS NOT NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE actors a
            SET account_id = acc.id
            FROM accounts acc
            WHERE acc.external_id = a.external_id AND a.type = 'HUMAN'
            """
        )
    )

    # 4. Funder attribution moves to the principal. Indexed like the old actor_id (funding lists/
    #    budget read by project, but the funder is resolved per-allocation in `_enrich`).
    op.add_column("funding_allocations", sa.Column("account_id", _uuid(), nullable=True))
    op.create_foreign_key(
        "fk_funding_allocations_account_id_accounts",
        "funding_allocations",
        "accounts",
        ["account_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_funding_allocations_account_id", "funding_allocations", ["account_id"]
    )

    # 5. Backfill funding → the funder actor's account. Today every funder is a human/internal
    #    actor (Phase 0 audit), whose account was created in step 3, so account_id resolves.
    op.execute(
        sa.text(
            """
            UPDATE funding_allocations f
            SET account_id = a.account_id
            FROM actors a
            WHERE f.actor_id = a.id
            """
        )
    )

    # 6. One primary `human` Actor per Account (Decision #7), now that every human is linked.
    #    Mirrors the model's __table_args__ index 1:1 (name, column, predicate).
    op.create_index(
        "uq_actors_one_human_per_account",
        "actors",
        ["account_id"],
        unique=True,
        postgresql_where=sa.text("type = 'HUMAN'"),
    )

    # 7-9. Drop the relocated columns. Postgres cascades each column's dependent objects: the
    #      funding actor_id index + FK, and the actors.external_id unique constraint + index.
    op.drop_column("funding_allocations", "actor_id")
    op.drop_column("actors", "external_id")
    op.drop_column("actors", "roles")


def downgrade() -> None:
    # Re-add the dropped columns in their pre-0006 shapes (baseline / 0004), all nullable/defaulted
    # so the add itself never fails on existing rows.
    op.add_column("actors", sa.Column("external_id", sa.String(length=255), nullable=True))
    op.create_unique_constraint("actors_external_id_key", "actors", ["external_id"])
    op.add_column(
        "actors",
        sa.Column(
            "roles",
            postgresql.ARRAY(sa.String()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
    )
    op.add_column("funding_allocations", sa.Column("actor_id", _uuid(), nullable=True))
    op.create_foreign_key(
        "funding_allocations_actor_id_fkey",
        "funding_allocations",
        "actors",
        ["actor_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_funding_allocations_actor_id", "funding_allocations", ["actor_id"]
    )

    # Re-derive the moved data from accounts — human actors only, restoring the original invariant
    # that *only* `human` actors carry external_id/roles (agents/system keep NULL / '{}'). One human
    # per account (the partial index, still present here) guarantees no duplicate external_id.
    op.execute(
        sa.text(
            """
            UPDATE actors a
            SET external_id = acc.external_id, roles = acc.roles
            FROM accounts acc
            WHERE a.account_id = acc.id AND a.type = 'HUMAN'
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE funding_allocations f
            SET actor_id = a.id
            FROM actors a
            WHERE a.account_id = f.account_id AND a.type = 'HUMAN'
            """
        )
    )

    # Tear down the additive objects (after the backfill, which still reads account_id).
    op.drop_index("uq_actors_one_human_per_account", table_name="actors")
    op.drop_index("ix_funding_allocations_account_id", table_name="funding_allocations")
    op.drop_constraint(
        "fk_funding_allocations_account_id_accounts",
        "funding_allocations",
        type_="foreignkey",
    )
    op.drop_column("funding_allocations", "account_id")
    op.drop_constraint("fk_actors_account_id_accounts", "actors", type_="foreignkey")
    op.drop_column("actors", "account_id")
    op.drop_table("accounts")
