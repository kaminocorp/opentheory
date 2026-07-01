from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ResultStatus


class ToolInvocation(BaseModel):
    """One blame-tuple entry in ``Checkpoint.tool_invocations`` — the toolbench provenance spine.

    The ``(tool, version, inputs) -> output`` record that makes a tool-produced result reproducible
    and blamable: *which instrument + version, on which engine + version, from which inputs, under
    what assumptions, with what status.* Together with the ``assumptions`` captured on the
    ``Evidence``/``Artifact``, this is the *only* mandatory per-result record — everything else
    (exact / approximate / retrieved, and any future grade) is **derivable** from the recorded
    instrument, never stamped (``docs/plans/maths-toolbox.md`` cross-cutting 2).

    **Strict on write** (this model): every entry a write path records must parse as this exact
    shape (``extra="forbid"`` rejects a mistyped key, so a malformed tuple can never reach the
    ledger). **Lenient on read**: the checkpoint read surfaces ``tool_invocations`` as raw JSON
    (``list[dict]``), so a pre-shape historical entry — or a future-shape one — can never 500 a
    project read. This mirrors the ``AgentModels`` lenient-read / strict-write split (0.8.10).

    It rides as validated JSON on the **append-only** ``Checkpoint`` rather than a dedicated table,
    so its immutability comes free from the checkpoint guard (plan Decision 2). A dedicated
    ``tool_invocations`` table is deferred until cross-invocation audit queries ("all results from
    SymPy 1.13") demand it.
    """

    model_config = ConfigDict(extra="forbid")

    instrument: str = Field(min_length=1)  # e.g. "geometry.coordinate_measure"
    instrument_version: str = Field(min_length=1)  # our adapter version, e.g. "0.1.0"
    engine: str = Field(min_length=1)  # e.g. "sympy"
    engine_version: str = Field(min_length=1)  # pinned engine version, for reproduction
    inputs: dict[str, Any]  # the exact validated inputs
    output: dict[str, Any]  # the result (a number carries its own tolerance/bound)
    assumptions: dict[str, Any] = Field(default_factory=dict)  # what it was computed under
    status: ResultStatus
    # Set by the write path once the produced Artifact has an id (plan Phase 3). Optional here so a
    # tuple can be built before the artifact is flushed and stamped afterwards.
    produced_artifact_id: UUID | None = None
