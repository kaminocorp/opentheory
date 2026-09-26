"""``table.create`` — build a table artifact from typed rows/columns.

This is a *container*, not a computation. It canonicalizes cells (exact math stays
exact; labels stay labels) and lands a ``table`` artifact. It never refutes and
never contributes a grounding grade — pointing a claim at a table you just typed
is not evidence that the claim is true.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ResultStatus
from app.toolbench.adapter import InstrumentResult
from app.toolbench.instruments._table_support import (
    ENGINE,
    ENGINE_VERSION,
    TablePayload,
    normalize_table,
)


class TableCreateInput(TablePayload):
    """Same shape as the shared table payload — columns, rows, optional title."""


class TableCreateOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    columns: list[str]
    rows: list[dict[str, str]]
    n_rows: int
    n_cols: int
    has_labels: bool
    exact: bool = Field(
        description="True when no cell was an inexact float — labels may still be present."
    )


class TableCreate:
    name = "table.create"
    namespace = "table"
    version = "0.1.0"
    engine = ENGINE
    engine_version = ENGINE_VERSION
    description = (
        "Build a table artifact from typed rows and columns. Cells are exact integers / "
        "rationals / expressions, or opaque labels — floats are rejected. A table is a "
        "container, not evidence."
    )
    InputModel = TableCreateInput
    OutputModel = TableCreateOutput

    def run(self, inputs: TableCreateInput, assumptions: dict[str, Any]) -> InstrumentResult:
        table = normalize_table(inputs, allow_labels=True, assumptions=assumptions)
        payload = TableCreateOutput.model_validate(table.as_output()).model_dump(mode="json")
        return InstrumentResult(
            output=payload,
            status=ResultStatus.RESULT,
            artifact_kind="table",
        )


TABLE_CREATE = TableCreate()
