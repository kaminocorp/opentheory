from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AccountBase(BaseModel):
    display_name: str = Field(min_length=1, max_length=200)
    external_id: str | None = Field(default=None, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    roles: list[str] = Field(default_factory=list)


class AccountCreate(AccountBase):
    # Dev/test bootstrap (behind auth_dev_header_enabled): inherits the seed fields removed from
    # ActorCreate (external_id, roles). Production accounts are JIT-provisioned with their primary
    # human Actor on first sign-in (api/deps.py); this route exists only to let tests build an
    # internal funder without seeding (Decision #8).
    account_metadata: dict[str, Any] = Field(default_factory=dict)


class AccountRead(AccountBase):
    """Full account read — exposes external_id + email + roles, so any endpoint returning it must
    be gated (authenticated /me for the owner; dev-gated /accounts). This is the 0.6.1 PII class,
    moved here with the fields."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime


class AccountSummary(BaseModel):
    """Minimal funder identity for public display (nested in FundingRead).

    Deliberately **omits email/roles/external_id**: the funding read endpoints are unauthenticated
    (api/routes/funding.py), so this is the privacy-preserving mirror of ``ActorSummary`` — the
    public funding history shows *who* funded (display name), never their contact PII.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    display_name: str
