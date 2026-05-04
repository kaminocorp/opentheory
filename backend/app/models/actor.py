from typing import Any

from sqlalchemy import JSON, Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin
from app.models.enums import ActorType


class Actor(IdMixin, TimestampMixin, Base):
    __tablename__ = "actors"

    type: Mapped[ActorType] = mapped_column(Enum(ActorType, name="actor_type"), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    actor_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    contributions = relationship("Contribution", back_populates="actor")
    funding_allocations = relationship("FundingAllocation", back_populates="actor")
    checkpoints = relationship("Checkpoint", back_populates="author")
    validations = relationship("Validation", back_populates="actor")
