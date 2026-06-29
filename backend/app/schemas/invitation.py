from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import InvitationStatus, ProjectRole
from app.schemas.account import AccountSummary


class InvitationCreate(BaseModel):
    """Body for ``POST /projects/{id}/invitations`` (0.8.7).

    ``identifier`` is a free-text ``@username`` **or** email, resolved server-side by
    ``resolve_account_by_identifier`` (existing users only — there is no "invite someone not yet
    signed up" path). ``role`` is the membership granted on accept; only ``ADMIN`` is meaningful
    today (you cannot invite a second ``OWNER`` — the partial unique index forbids it), so it
    defaults to ``ADMIN``.
    """

    identifier: str = Field(min_length=1, max_length=255)
    role: ProjectRole = ProjectRole.ADMIN


class InvitationRead(BaseModel):
    """A project invitation for both the project-side list and the invitee's bell inbox (0.8.7).

    Carries the project title (so the inbox can show "you were invited to X" without a second
    fetch) and **privacy-safe ``AccountSummary``** for both the invitee and the inviter — never
    email/roles/external_id — so it is safe to serve to the invitee (who is not a project member
    yet). Constructed explicitly in the service (project title + summaries are a join, not a single
    ORM attribute).
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    project_title: str
    role: ProjectRole
    status: InvitationStatus
    invitee: AccountSummary
    invited_by: AccountSummary | None
    created_at: datetime
    updated_at: datetime
