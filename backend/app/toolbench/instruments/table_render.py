"""``table.render`` — serialize a table for the ledger / UI.

Display, not compute. The artifact is the same structured table plus a markdown
serialization the workspace can show. Never a grade — rendering a grid does not
support or refute a claim.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.enums import ResultStatus
from app.toolbench.adapter import InstrumentResult
from app.toolbench.instruments._table_support import (
    ENGINE,
    ENGINE_VERSION,
    TablePayload,
    normalize_table,
    render_markdown,
)


class TableRenderInput(TablePayload):
    """Columns + rows to display. Optional title rides on the markdown heading line."""


class TableRenderOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    columns: list[str]
    rows: list[dict[str, str]]
    n_rows: int
    n_cols: int
    has_labels: bool
    exact: bool
    markdown: str


class TableRender:
    name = "table.render"
    namespace = "table"
    version = "0.1.0"
    engine = ENGINE
    engine_version = ENGINE_VERSION
    description = (
        "Display and serialize a table for the ledger. Same exact-cell rules as "
        "table.create. Presentation only — not evidence."
    )
    InputModel = TableRenderInput
    OutputModel = TableRenderOutput

    def run(self, inputs: TableRenderInput, assumptions: dict[str, Any]) -> InstrumentResult:
        table = normalize_table(inputs, allow_labels=True, assumptions=assumptions)
        payload = TableRenderOutput(
            **table.as_output(),
            markdown=render_markdown(table),
        ).model_dump(mode="json")
        return InstrumentResult(
            output=payload,
            status=ResultStatus.RESULT,
            artifact_kind="table",
        )


TABLE_RENDER = TableRender()
