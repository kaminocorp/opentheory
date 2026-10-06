"""AgentSessionToken — OWNER-minted harness session credential (0.53.0 schema).

Mutable (revoke in place). Not a ledger primitive and **not** append-only —
do **not** register it in ``models/append_only.py``. Hash of the compact JWT
is stored; the bearer is shown once at mint. Mint / verify / resolver landed
in ``0.55.0``.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, LargeBinary, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin


class AgentSessionToken(IdMixin, TimestampMixin, Base):
    __tablename__ = "agent_session_tokens"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_agent_session_tokens_hash"),
        Index(
            "ix_agent_session_tokens_lookup",
            "actor_id",
            "project_id",
            "revoked_at",
            "expires_at",
        ),
    )

    # ``id`` is also the JWT ``jti``.
    project_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("actors.id", ondelete="CASCADE"),
        nullable=False,
    )
    minted_by_account_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="SET NULL"),
    )
    minted_by_actor_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("actors.id", ondelete="SET NULL"),
    )
    # SHA-256 of the compact JWT; the bearer is never stored.
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Null = live. Revoke is the control; expiry is the backstop.
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project = relationship("Project", back_populates="agent_session_tokens")
    actor = relationship("Actor", foreign_keys=[actor_id])
    minted_by_account = relationship("Account", foreign_keys=[minted_by_account_id])
    minted_by_actor = relationship("Actor", foreign_keys=[minted_by_actor_id])
