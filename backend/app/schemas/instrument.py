from typing import Any

from pydantic import BaseModel

from app.models.enums import ResultStatus


class ResultContractOutcome(BaseModel):
    """One of the three honest outcomes, surfaced with its meaning so the catalog self-describes.

    The contract is *universal* — every instrument can, in principle, return any of the three — so
    the same three entries ride on every :class:`InstrumentDescriptor`; the UI reads one entry and
    knows how to render each outcome (e.g. ``undecided`` must render as "escalate", never a pass).
    """

    status: ResultStatus
    meaning: str


class InstrumentDescriptor(BaseModel):
    """A read-only description of one instrument, served to the UI / agent API (Phase 6).

    ``input_schema`` / ``output_schema`` are real JSON Schema from the instrument's Pydantic
    ``InputModel`` / ``OutputModel`` (``model_json_schema()``), so a client can render a form and
    validate a payload without any server round-trip. Static reference data, like the agent-model
    catalog — cacheable indefinitely.
    """

    name: str
    namespace: str
    version: str
    engine: str
    engine_version: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    result_contract: list[ResultContractOutcome]
