from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Enum, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin
from app.models.enums import ActorType


class Actor(IdMixin, TimestampMixin, Base):
    __tablename__ = "actors"

    # One primary `human` Actor per Account (Decision #7): a partial unique index on
    # `account_id` scoped to `type = 'HUMAN'`. `agent` actors are unconstrained (an account may own
    # many); `system` / dev-bootstrap actors have `account_id IS NULL` (excluded). Declared here so
    # `Base.metadata.create_all` (the test harness) builds the *same* constraint migration 0006
    # installs in prod — keeping create_all and Alembic in lockstep. The enum label is uppercase
    # ('HUMAN' is the StrEnum member name, this DB's enum convention).
    __table_args__ = (
        Index(
            "uq_actors_one_human_per_account",
            "account_id",
            unique=True,
            postgresql_where=text("type = 'HUMAN'"),
        ),
    )

    type: Mapped[ActorType] = mapped_column(Enum(ActorType, name="actor_type"), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    actor_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    # The owning principal (0.7.0, Account-owns-Actor). Nullable: `system` actors and
    # dev-bootstrap actors (X-Dev-Actor-Id) have no account; a `human` actor's account is its
    # login. `external_id` and `roles` moved to `accounts` — auth resolves the Actor via
    # `Account.external_id`, and `internal` lives on the account now. The one-`human`-per-account
    # rule is the partial unique index in `__table_args__` above (mirrored by migration 0006).
    account_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="SET NULL"),
    )

    account = relationship("Account", back_populates="actors")
    contributions = relationship("Contribution", back_populates="actor")
    checkpoints = relationship("Checkpoint", back_populates="author")
    validations = relationship("Validation", back_populates="actor")
