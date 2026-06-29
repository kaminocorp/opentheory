from typing import Any

from sqlalchemy import JSON, Index, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin


class Account(IdMixin, TimestampMixin, Base):
    """The authentication *principal* (0.7.0) — one per Supabase ``auth.users`` login — that
    **owns** one or more ``Actor``s.

    Holds principal-level concerns moved off ``actors``: the IdP subject (``external_id`` = the
    JWT ``sub``, the key auth resolves on), the contact ``email``, and ``roles`` (``internal``
    gates native funding). Funding attribution points at the ``Account`` (money is the
    principal's); research provenance stays on ``Actor`` (see ``account-owns-actor.md``).

    Mutable identity row — like ``Branch.status`` and the old ``actors.roles`` it is **not**
    append-only guarded; do **not** register it in ``models/append_only.py``.
    """

    __tablename__ = "accounts"
    # The unique handle constraint is named (not the column-level `unique=True` auto-name) so the
    # test harness's `create_all` builds exactly what migration `0008` installs — the
    # `uq_actors_one_human_per_account` discipline.
    __table_args__ = (
        UniqueConstraint("username", name="uq_accounts_username"),
        # Case-insensitive email lookup for invite resolution (`resolve_account_by_identifier`):
        # the resolver matches on `lower(email)`, so index that expression to keep it off a seq scan
        # as `accounts` grows. Non-unique — `email` is intentionally not uniqueness-enforced
        # (proposal §7); an ambiguous email becomes a 409 in the invite service, not a constraint.
        Index("ix_accounts_email_lower", text("lower(email)")),
    )

    # The IdP subject (`sub`); the unique key auth resolves on, moved here from `actors`. Nullable
    # so a future org/service account without a single `sub` is representable — the human-provision
    # path always sets it.
    external_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    # The public ``@handle`` (0.8.3): unique, lowercased, renameable. Distinct from `display_name`
    # (free-form, non-unique) and `email` (private). Auto-generated on first sign-in
    # (api/deps.py) so every principal has one immediately — no "choose a username" gate. The
    # uniqueness is enforced by `uq_accounts_username` (above), not a column-level `unique=True`.
    username: Mapped[str] = mapped_column(String(30), nullable=False)
    # Promoted out of `actor_metadata`: the principal's contact email.
    email: Mapped[str | None] = mapped_column(String(255))
    # Queryable authorization (moved from `actors.roles`, Decision #4). `internal` gates native
    # funding and is the substrate for validator/agent permissions later. Mutable identity
    # attribute, not a ledger event — so it is *not* append-only guarded.
    roles: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list, server_default=text("'{}'")
    )
    account_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    actors = relationship("Actor", back_populates="account")
    funding_allocations = relationship("FundingAllocation", back_populates="account")
