"""Typed failures for the toolbench execution sandbox (0.11.x).

These exceptions are raised when an instrument run cannot complete within resource limits or when
the machine is at capacity. They map to HTTP statuses in ``services/tool_runs.py`` (Phase 3) and
must propagate **before** any ledger rows are minted.
"""

from typing import Literal

TerminationReason = Literal["timeout", "memory", "busy", "worker_error"]


class ToolbenchExecutionError(Exception):
    """Base for sandbox failures — carries attribution metadata for logs and API responses."""

    reason: TerminationReason

    def __init__(
        self,
        *,
        instrument_name: str,
        reason: TerminationReason,
        wall_ms: float | None = None,
        message: str | None = None,
    ) -> None:
        self.instrument_name = instrument_name
        self.reason = reason
        self.wall_ms = wall_ms
        detail = message or self._default_message()
        super().__init__(detail)

    def _default_message(self) -> str:
        return f"Instrument {self.instrument_name!r} did not complete ({self.reason})"


class ToolbenchTimeout(ToolbenchExecutionError):
    """Wall-clock budget exceeded — child was terminated."""

    def __init__(
        self,
        *,
        instrument_name: str,
        wall_ms: float | None = None,
        message: str | None = None,
    ) -> None:
        super().__init__(
            instrument_name=instrument_name,
            reason="timeout",
            wall_ms=wall_ms,
            message=message,
        )


class ToolbenchMemoryExceeded(ToolbenchExecutionError):
    """Child exceeded the configured memory ceiling (RLIMIT_AS on Linux)."""

    def __init__(
        self,
        *,
        instrument_name: str,
        wall_ms: float | None = None,
        message: str | None = None,
    ) -> None:
        super().__init__(
            instrument_name=instrument_name,
            reason="memory",
            wall_ms=wall_ms,
            message=message,
        )


class ToolbenchBusy(ToolbenchExecutionError):
    """Concurrency semaphore not acquired within the acquire timeout."""

    def __init__(
        self,
        *,
        instrument_name: str,
        wall_ms: float | None = None,
        message: str | None = None,
    ) -> None:
        super().__init__(
            instrument_name=instrument_name,
            reason="busy",
            wall_ms=wall_ms,
            message=message,
        )


class ToolbenchWorkerError(ToolbenchExecutionError):
    """Child process failed unexpectedly (non-zero exit, crash, or malformed IPC)."""

    def __init__(
        self,
        *,
        instrument_name: str,
        wall_ms: float | None = None,
        message: str | None = None,
    ) -> None:
        super().__init__(
            instrument_name=instrument_name,
            reason="worker_error",
            wall_ms=wall_ms,
            message=message,
        )