from typing import Any

from sqlalchemy import JSON, String, text
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

    # The IdP subject (`sub`); the unique key auth resolves on, moved here from `actors`. Nullable
    # so a future org/service account without a single `sub` is representable — the human-provision
    # path always sets it.
    external_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
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
