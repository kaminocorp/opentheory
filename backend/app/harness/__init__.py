"""External DeepSeek Harness adapter (0.40–0.44).

Composition, fixture MCP, the live domain door, the fail-closed OpenRouter
gateway, the 0.43.0 session owner (``HarnessSession`` + odd-perfect
reference campaign), and the 0.44.0 fail-closed campaign composition
(session-owned child; unmetered probe is an explicit flag). Not imported
by the FastAPI app. Does not enable ``AGENT_LOOP_ENABLED``. Ledger writes
go only through ``run_instrument`` / ``create_checkpoint``. Token spend
debits ``ComputeDebit`` on the session-owned gateway path.
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
