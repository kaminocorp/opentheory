from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import ResultStatus
from app.schemas.checkpoint import CheckpointRead


class ToolRunRequest(BaseModel):
    """Request body for ``POST /projects/{id}/instruments/{name}/run`` (Phase 6).

    ``inputs`` is the raw instrument payload — validated against the resolved instrument's
    ``InputModel`` *in the service* (a mismatch is a ``422``), not here, so the envelope stays
    generic across every instrument. ``assumptions`` are recorded on the produced Evidence/Artifact
    and in the blame tuple. ``thread_id`` scopes the result to a thread; ``claim_id`` (with an
    optional ``relation_kind`` override) also mints ``Evidence`` linked to that claim.
    """

    inputs: dict[str, Any]
    assumptions: dict[str, Any] = Field(default_factory=dict)
    thread_id: UUID | None = None
    claim_id: UUID | None = None
    relation_kind: str | None = None


class ToolRunResult(BaseModel):
    """What ``services/tool_runs.py::run_instrument`` returns — the durable, attributed result.

    Carries the ledger records the run produced: the ``Checkpoint`` (with its blame tuple, refs, and
    ``tool_run`` contribution surfaced via the enriched read), the produced ``Artifact`` id, and —
    when the run targeted a claim — the minted ``Evidence`` id. ``status`` and ``content_hash`` are
    lifted to the top level for convenience. Phase 6 wraps this in the HTTP response and adds the
    request body model; Phase 7 renders provenance from ``checkpoint.tool_invocations``.
    """

    checkpoint: CheckpointRead
    artifact_id: UUID
    evidence_id: UUID | None = None
    status: ResultStatus
    content_hash: str
