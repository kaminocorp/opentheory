from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.usernames import RESERVED_USERNAMES, USERNAME_PATTERN


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


class AccountUpdate(BaseModel):
    """Self-service identity edit for ``PATCH /me`` (0.8.3). Only the public ``username`` for now.

    Normalizes (lowercase/trim) **before** validating so ``Foo`` is accepted as ``foo``, then
    enforces the ``^[a-z0-9_]{3,30}$`` shape and rejects the reserved set — both as a
    ``ValueError`` → ``422``. Uniqueness is a DB concern (the route translates the collision to a
    ``409``), not validated here.
    """

    username: str

    @field_validator("username")
    @classmethod
    def _normalize_and_validate(cls, value: str) -> str:
        candidate = value.strip().lower()
        if not USERNAME_PATTERN.match(candidate):
            raise ValueError(
                "username must be 3–30 characters of lowercase letters, digits, or underscores"
            )
        if candidate in RESERVED_USERNAMES:
            raise ValueError("that username is reserved")
        return candidate


class AccountRead(AccountBase):
    """Full account read — exposes external_id + email + roles, so any endpoint returning it must
    be gated (authenticated /me for the owner; dev-gated /accounts). This is the 0.6.1 PII class,
    moved here with the fields."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    # Public handle (0.8.3) — fine to expose even on the gated read.
    username: str
    created_at: datetime
    updated_at: datetime


class AccountSummary(BaseModel):
    """Minimal account identity for public display (nested in FundingRead / ProjectMemberRead).

    Deliberately **omits email/roles/external_id**: the funding/member read endpoints are
    unauthenticated, so this is the privacy-preserving mirror of ``ActorSummary`` — the public
    surface shows *who* (display name + ``@username``), never their contact PII. ``username`` is a
    public handle, so it is safe (and necessary, for invites) to expose here.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    display_name: str
    username: str
