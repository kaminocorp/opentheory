"""External DeepSeek Harness adapter (0.40–0.48).

Composition, fixture MCP, the live domain door, the fail-closed OpenRouter
gateway, the 0.43.0 session owner (``HarnessSession`` + odd-perfect
reference campaign), the 0.44.0 fail-closed campaign composition
(session-owned child; unmetered probe is an explicit flag), the
0.46.0 daily token cap (today's ``harness_session_turn`` ``ComputeDebit``
sum; survives a process restart), the 0.47.0 remaining-room hold
that closes the overlapping-authorize race, and the 0.48.0 stale-hold
release so a crash after authorize does not pin the UTC day. Not
imported by the FastAPI app. Does not enable ``AGENT_LOOP_ENABLED``.
Ledger writes go only through ``run_instrument`` / ``create_checkpoint``.
Token spend debits ``ComputeDebit`` on the session-owned gateway path.
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
