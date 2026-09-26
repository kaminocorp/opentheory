"""External DeepSeek Harness adapter (`0.40.0` composition + `0.41.0` live MCP).

Composition, fixture MCP (M0 probe), and the live domain door. Not imported
by the FastAPI app. Does not enable ``AGENT_LOOP_ENABLED``. Ledger writes go
only through ``run_instrument`` / ``create_checkpoint``.
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
