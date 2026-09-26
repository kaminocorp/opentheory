"""External DeepSeek Harness adapter — Milestone 0 (`0.40.0`).

Composition + fixture MCP only. Not imported by the FastAPI app. Does not
enable ``AGENT_LOOP_ENABLED``. Does not write the ledger.
"""

from app.harness.composition import (
    TOOL_NAMES,
    TOOL_STEMS,
    VERSION,
    CompositionError,
    verify,
)

__all__ = [
    "TOOL_NAMES",
    "TOOL_STEMS",
    "VERSION",
    "CompositionError",
    "verify",
]
