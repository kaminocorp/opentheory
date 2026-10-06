"""ProjectAgentMember — the per-project agent roster (0.53.0).

One row is "this agent Actor is deployed on this project." It is access
control / governance, **not** intellectual credit: it never touches
``Contribution`` / ``Validation`` / ``FundingAllocation``. Membership is
**not** inherited from the sponsor Account — ``ProjectMember`` stays
human-account governance.

Mutable identity/governance row (suspend / resume / revoke is an in-place
edit, not a ledger event) — like ``ProjectMember`` and ``Account``, it is
**not** append-only guarded; do **not** register it in
``models/append_only.py``.
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import Enum, ForeignKey, Index, Integer, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin
from app.models.enums import ProjectAgentRole, ProjectAgentStatus


class ProjectAgentMember(IdMixin, TimestampMixin, Base):
    __tablename__ = "project_agent_members"
    __table_args__ = (
        # One roster row per (project, actor): re-adding an existing pair is a
        # conflict, not a second row. Resume of a revoked actor is an in-place
        # status change.
        UniqueConstraint("project_id", "actor_id", name="uq_project_agent_member"),
        Index("ix_project_agent_members_project_status", "project_id", "status"),
        # OWNER-transfer lookup: suspend rows whose responsible account is the
        # outgoing owner (0.54.0).
        Index(
            "ix_project_agent_members_responsible",
            "project_id",
            "responsible_account_id",
        ),
    )

    project_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Service requires ``actors.type = 'AGENT'`` (not a cross-table CHECK).
    # CASCADE: a removed Actor drops its roster seats.
    actor_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("actors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Who put this row on the roster (historical). Never rewritten on OWNER
    # transfer. SET NULL so an account removal does not cascade-delete the seat.
    deployed_by_account_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="SET NULL"),
    )
    # Who is on the hook now. Equals deployer at insert; set to the new OWNER
    # on resume. Transfer trigger (0.54.0) keys on this, not deployed_by.
    responsible_account_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="SET NULL"),
    )
    role: Mapped[ProjectAgentRole] = mapped_column(
        Enum(ProjectAgentRole, name="project_agent_role"),
        nullable=False,
    )
    status: Mapped[ProjectAgentStatus] = mapped_column(
        Enum(ProjectAgentStatus, name="project_agent_status"),
        nullable=False,
        default=ProjectAgentStatus.ACTIVE,
        server_default="ACTIVE",
    )
    # Stored in v1; enforced in a later slice. Null = no per-agent ceiling
    # (project pot + project daily cap only).
    token_budget_cap: Mapped[int | None] = mapped_column(Integer, nullable=True)
    usd_budget_cap: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)

    project = relationship("Project", back_populates="agent_members")
    actor = relationship("Actor", foreign_keys=[actor_id])
    deployed_by = relationship("Account", foreign_keys=[deployed_by_account_id])
    responsible = relationship("Account", foreign_keys=[responsible_account_id])
