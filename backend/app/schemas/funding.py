from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import FundingKind, FundingSource, FundingStatus
from app.schemas.checkpoint import ActorSummary


class FundingCreate(BaseModel):
    """Create payload for a funding allocation. ``status`` is server-decided (Decision #5):
    ``native`` is born ``settled``; ``stripe`` is born ``pending`` (no real settlement here)."""

    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    kind: FundingKind = FundingKind.TOP_UP
    source: FundingSource = FundingSource.NATIVE
    notes: str | None = None

    @field_validator("currency")
    @classmethod
    def _upper_currency(cls, value: str) -> str:
        return value.upper()


class FundingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    actor_id: UUID | None
    actor: ActorSummary | None = None
    amount: Decimal
    currency: str
    kind: FundingKind
    source: FundingSource
    status: FundingStatus
    notes: str | None
    created_at: datetime
    updated_at: datetime


class ProjectBudget(BaseModel):
    """Project budget derived from the funding ledger (0.6.3).

    ``funded`` = Σ settled allocations; ``spent`` = 0 until agents meter compute (0.7.0,
    Decision #6); ``available`` = funded − spent. Amounts are summed in a single accounting
    unit (``currency``); multi-currency funding is out of scope for this release.
    """

    project_id: UUID
    currency: str
    funded: Decimal
    spent: Decimal
    available: Decimal
    # Settled totals keyed by FundingSource value (e.g. {"native": "500.00"}).
    by_source: dict[str, Decimal] = Field(default_factory=dict)
    # Totals keyed by FundingStatus value across all allocations (settled, pending, ...).
    by_status: dict[str, Decimal] = Field(default_factory=dict)
