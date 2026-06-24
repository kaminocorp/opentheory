from decimal import Decimal
from uuid import UUID

from sqlalchemy import Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin
from app.models.enums import FundingKind, FundingSource, FundingStatus


class FundingAllocation(IdMixin, TimestampMixin, Base):
    __tablename__ = "funding_allocations"

    project_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("actors.id", ondelete="SET NULL"),
        index=True,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    kind: Mapped[FundingKind] = mapped_column(
        Enum(FundingKind, name="funding_kind"),
        nullable=False,
    )
    # Where the budget came from (0.6.3): native (Kamino comps) vs stripe (external). Orthogonal
    # to `kind` (the accounting category). Native is gated to internal actors in the service.
    source: Mapped[FundingSource] = mapped_column(
        Enum(FundingSource, name="funding_source"),
        nullable=False,
    )
    status: Mapped[FundingStatus] = mapped_column(
        Enum(FundingStatus, name="funding_status"),
        default=FundingStatus.PENDING,
        nullable=False,
    )
    payment_reference: Mapped[str | None] = mapped_column(String(255), index=True)
    notes: Mapped[str | None] = mapped_column(Text)

    project = relationship("Project", back_populates="funding_allocations")
    actor = relationship("Actor", back_populates="funding_allocations")
    contributions = relationship("Contribution", back_populates="funding_allocation")
