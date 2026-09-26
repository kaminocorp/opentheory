"""External DeepSeek Harness adapter (0.40 composition, 0.41 live MCP, 0.42 gateway).

Composition, fixture MCP, the live domain door, and the fail-closed OpenRouter
gateway + turn supervision. Not imported by the FastAPI app. Does not enable
``AGENT_LOOP_ENABLED``. Ledger writes go only through ``run_instrument`` /
``create_checkpoint``. Token spend debits ``ComputeDebit``.
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
