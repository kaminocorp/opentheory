from uuid import UUID

from sqlalchemy import Enum, ForeignKey, Index, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin
from app.models.enums import ProjectRole


class ProjectMember(IdMixin, TimestampMixin, Base):
    """Project-level membership (0.8.1) — the platform's first project authorization primitive.

    A membership ties an ``Account`` (the principal, 0.7.0) to a ``Project`` with a ``ProjectRole``.
    It is access control / governance, **not** intellectual credit: it grants the capability to
    edit a project but confers no authorship, validation, or funding attribution (those live on
    ``Contribution`` / ``Validation`` / ``FundingAllocation``). Keyed on the *account* — like
    ``username`` and (later) invitations — so an agent actor owned by an admin account later
    inherits the same edit capability through the same API, no parallel model.

    Mutable identity/governance row (a role change is an in-place edit, not a ledger event) — like
    ``Account`` and ``Branch.status``, it is **not** append-only guarded; do not register it in
    ``models/append_only.py``.
    """

    __tablename__ = "project_members"
    __table_args__ = (
        # One membership row per (project, account): re-adding an existing member is a conflict, not
        # a second row.
        UniqueConstraint("project_id", "account_id", name="uq_project_member"),
        # At most one OWNER per project (Decision: exactly one owner; superset of admin). Declared
        # here *and* in migration 0007 so the test harness's ``Base.metadata.create_all`` builds the
        # same constraint Alembic installs (the ``uq_actors_one_human_per_account`` discipline). The
        # enum label is the uppercase StrEnum member name (this DB's named-enum convention).
        Index(
            "uq_project_one_owner",
            "project_id",
            unique=True,
            postgresql_where=text("role = 'OWNER'"),
        ),
    )

    project_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    account_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[ProjectRole] = mapped_column(
        Enum(ProjectRole, name="project_role"),
        nullable=False,
    )
    # Provenance: who invited this member (the owner self-references on create). SET NULL so an
    # inviter's account removal doesn't cascade-delete the membership it created.
    invited_by_account_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="SET NULL"),
    )

    project = relationship("Project", back_populates="members")
    account = relationship("Account", foreign_keys=[account_id])
