from uuid import UUID

from sqlalchemy import Enum, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin
from app.models.enums import InvitationStatus, ProjectRole


class ProjectInvitation(IdMixin, TimestampMixin, Base):
    """An invitation for an existing account to collaborate on a project (0.8.7).

    Sits one step before ``ProjectMember``: an owner/admin invites a known principal (resolved by
    ``@username`` or email) to a ``ProjectRole`` (``ADMIN`` for now); the invitee then accepts
    (which mints the ``ProjectMember``) or declines. Like membership, it is access control /
    governance — **not** intellectual credit — so it lives in its own table and never touches
    ``Contribution`` / ``Validation`` / ``FundingAllocation``.

    A ``UniqueConstraint(project_id, invitee_account_id)`` means there is at most **one** invitation
    row per (project, invitee): re-inviting a declined/revoked user is an *upsert* that resets the
    same row to ``PENDING``, never a second row. Mutable governance row (the status moves through
    its lifecycle in place) — like ``ProjectMember`` / ``Account`` / ``Branch.status``, it is
    deliberately **not** registered in ``models/append_only.py``.
    """

    __tablename__ = "project_invitations"
    __table_args__ = (
        # One invitation row per (project, invitee): re-inviting resets this row, not a new one.
        UniqueConstraint("project_id", "invitee_account_id", name="uq_project_invitation"),
    )

    project_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    invitee_account_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[ProjectRole] = mapped_column(
        Enum(ProjectRole, name="project_role"),
        default=ProjectRole.ADMIN,
        nullable=False,
    )
    status: Mapped[InvitationStatus] = mapped_column(
        Enum(InvitationStatus, name="invitation_status"),
        default=InvitationStatus.PENDING,
        nullable=False,
    )
    # Provenance: who issued the invite. SET NULL so the inviter's account removal doesn't
    # cascade-delete the invitation (mirrors ProjectMember.invited_by_account_id).
    invited_by_account_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="SET NULL"),
    )

    project = relationship("Project", back_populates="invitations")
    invitee = relationship("Account", foreign_keys=[invitee_account_id])
    invited_by = relationship("Account", foreign_keys=[invited_by_account_id])
