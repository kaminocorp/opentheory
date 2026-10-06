"""Agent definition catalog (0.59.0). Versioned kind owned by an Account."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AgentDefinitionCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=200)
    config: dict[str, Any] = Field(default_factory=dict)


class AgentDefinitionPatch(BaseModel):
    """Cosmetic rename only. Config changes are a new version."""

    display_name: str = Field(min_length=1, max_length=200)


class AgentDefinitionVersionCreate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    config: dict[str, Any] = Field(default_factory=dict)


class AgentDefinitionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    account_id: UUID | None
    family_id: UUID
    version: int
    display_name: str
    config_fingerprint: str
    config: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class AgentFamilyActorRead(BaseModel):
    actor_id: UUID
    project_id: UUID | None
    display_name: str
    definition_id: UUID
    definition_version: int


class AgentFamilyRollupRead(BaseModel):
    family_id: UUID
    versions: list[AgentDefinitionRead]
    actors: list[AgentFamilyActorRead]
    checkpoints_authored: int
    incoming_validations: int
    tokens_billed: int
    amount_billed: Decimal
