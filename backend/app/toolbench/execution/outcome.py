"""Execution outcome + resource metadata for the blame tuple (0.11.x Phase 5)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.toolbench.adapter import InstrumentResult
from app.toolbench.execution.policy import ExecutionLimits

SandboxMode = Literal["subprocess", "in-thread", "async"]
TerminationTag = Literal["timeout", "memory", "busy", "worker_error"]

ALLOWED_RESOURCE_USED_KEYS = frozenset(
    {"wall_ms", "sandbox", "memory_limit_mb", "terminated"}
)


@dataclass(frozen=True, slots=True)
class ExecutionOutcome:
    """Instrument result plus operator-facing resource metadata for the blame tuple."""

    result: InstrumentResult
    resource_used: dict[str, Any]


def build_resource_used(
    *,
    wall_ms: float,
    sandbox: SandboxMode,
    limits: ExecutionLimits,
    terminated: TerminationTag | None = None,
) -> dict[str, Any]:
    """Build a blame-tuple ``resource_used`` payload (presentation only — never hashed)."""
    payload: dict[str, Any] = {
        "wall_ms": round(wall_ms, 1),
        "sandbox": sandbox,
    }
    if limits.memory_limit_mb > 0:
        payload["memory_limit_mb"] = limits.memory_limit_mb
    if terminated is not None:
        payload["terminated"] = terminated
    return payload