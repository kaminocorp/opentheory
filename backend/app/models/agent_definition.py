"""Versioned agent kind (0.59.0) — catalog row owned by an Account.

Not append-only: a cosmetic rename mutates the same version. A config
change is a *new* row (same ``family_id``, ``version += 1``). Actors
point at one version via ``actors.agent_definition_id``; that pointer
is deploy-time only (see ``Actor``).
"""

from typing import Any
from uuid import UUID

from sqlalchemy import JSON, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin


class AgentDefinition(IdMixin, TimestampMixin, Base):
    __tablename__ = "agent_definitions"
    __table_args__ = (
        UniqueConstraint("family_id", "version", name="uq_agent_definitions_family_version"),
        Index("ix_agent_definitions_account_id", "account_id"),
        Index("ix_agent_definitions_family_id", "family_id"),
    )

    account_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="SET NULL"),
    )
    family_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    config_fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    account = relationship("Account")
    actors = relationship("Actor", back_populates="agent_definition")
