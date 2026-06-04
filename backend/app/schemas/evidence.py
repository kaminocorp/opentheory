from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# Allowed evidence/claim relation kinds. Kept as a Literal (and re-validated in the
# service layer) rather than a Postgres enum while the vocabulary stabilises.
RelationKind = Literal["support", "weaken", "context"]


class EvidenceBase(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    source_type: str = Field(min_length=1, max_length=80)
    uri: str | None = None
    retrieved_at: datetime | None = None
    content_hash: str | None = Field(default=None, max_length=128)
    citation: str | None = None
    notes: str | None = None
    evidence_metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceCreate(EvidenceBase):
    """Create payload for evidence attached to a claim.

    Creates an ``Evidence`` row and a ``claim_evidence_links`` row in one transaction.
    ``project_id``/``thread_id`` are inherited from the parent claim.
    """

    relation_kind: RelationKind


class EvidenceRead(EvidenceBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    thread_id: UUID | None
    relation_kind: RelationKind
    link_id: UUID
    created_at: datetime
    updated_at: datetime
