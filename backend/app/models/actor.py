from typing import Any

from sqlalchemy import JSON, Enum, String, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin
from app.models.enums import ActorType


class Actor(IdMixin, TimestampMixin, Base):
    __tablename__ = "actors"

    type: Mapped[ActorType] = mapped_column(Enum(ActorType, name="actor_type"), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    actor_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    # Queryable authorization (0.6.1). An `internal` (Kamino) role gates native funding; the
    # column is the reusable substrate for validator/agent permissions later. Mutable identity
    # attribute (like Branch.status), not a ledger event — so it is *not* append-only guarded.
    roles: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list, server_default=text("'{}'")
    )

    contributions = relationship("Contribution", back_populates="actor")
    funding_allocations = relationship("FundingAllocation", back_populates="actor")
    checkpoints = relationship("Checkpoint", back_populates="author")
    validations = relationship("Validation", back_populates="actor")
