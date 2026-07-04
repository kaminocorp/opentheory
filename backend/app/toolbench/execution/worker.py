"""Child-process worker for sync toolbench instruments (0.11.x Phase 2).

The worker receives JSON-safe ``inputs`` / ``assumptions`` dicts and an ``instrument_name``,
bootstraps the code registry, and returns a small result envelope over a multiprocessing queue.
Instrument singletons are never pickled across processes.
"""

from __future__ import annotations

import logging
import signal
from inspect import isawaitable
from typing import Any

from pydantic import ValidationError

from app.toolbench.adapter import InstrumentResult
from app.toolbench.registry import registry

logger = logging.getLogger(__name__)

Envelope = dict[str, Any]


def _maybe_register_test_stubs() -> None:
    """Register test-only instruments when the test package is importable (pytest only)."""
    try:
        from tests.toolbench.stubs import register_test_instruments
    except ImportError:
        return
    register_test_instruments()


def _bootstrap_registry() -> None:
    import app.toolbench.instruments  # noqa: F401 — side-effect registration

    _maybe_register_test_stubs()


def _apply_memory_limit(memory_limit_mb: int) -> None:
    if memory_limit_mb <= 0:
        return
    try:
        import resource

        limit_bytes = memory_limit_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (limit_bytes, limit_bytes))
    except (AttributeError, OSError, ValueError) as exc:
        logger.warning(
            "Skipping RLIMIT_AS memory cap (%s MB): %s",
            memory_limit_mb,
            exc,
        )


def _execute_instrument(
    instrument_name: str,
    inputs_dict: dict[str, Any],
    assumptions: dict[str, Any],
) -> InstrumentResult:
    _bootstrap_registry()
    instrument = registry.get(instrument_name)
    if instrument is None:
        msg = f"Unknown instrument {instrument_name!r}"
        raise ValueError(msg)

    validated = instrument.InputModel.model_validate(inputs_dict)
    raw = instrument.run(validated, assumptions)
    if isawaitable(raw):
        msg = f"Instrument {instrument_name!r} returned an awaitable from a sync execution path"
        raise TypeError(msg)
    return raw


def _envelope_ok(result: InstrumentResult) -> Envelope:
    return {
        "ok": True,
        "result": result.model_dump(mode="json"),
    }


def _envelope_err(*, error: str, kind: str) -> Envelope:
    return {
        "ok": False,
        "error": error,
        "kind": kind,
    }


def run_instrument_in_child(
    instrument_name: str,
    inputs_dict: dict[str, Any],
    assumptions: dict[str, Any],
    *,
    memory_limit_mb: int,
    result_queue: Any,
) -> None:
    """Top-level child entry — importable and picklable for ``multiprocessing`` spawn."""
    try:
        _apply_memory_limit(memory_limit_mb)
        result = _execute_instrument(instrument_name, inputs_dict, assumptions)
        result_queue.put(_envelope_ok(result))
    except (ValueError, ValidationError) as exc:
        result_queue.put(_envelope_err(error=str(exc), kind="value_error"))
    except MemoryError:
        # RLIMIT_AS trips as a Python MemoryError inside the child (an external cgroup OOM kill, by
        # contrast, SIGKILLs the child and never reaches here — the parent classifies that from the
        # exit code). Tag it so the parent raises ToolbenchMemoryExceeded → the resource-limit 422,
        # not a generic worker error. Reporting needs almost no memory (the failed allocation has
        # unwound); if even that fails, the parent's exit-code path still surfaces a failure.
        try:
            result_queue.put(
                _envelope_err(error="Instrument exceeded the memory limit", kind="memory")
            )
        except Exception:
            pass
    except Exception as exc:
        result_queue.put(_envelope_err(error=str(exc), kind="worker_error"))


def run_instrument_in_thread(
    instrument_name: str,
    inputs_dict: dict[str, Any],
    assumptions: dict[str, Any],
) -> InstrumentResult:
    """In-thread fallback when subprocess sandbox is disabled (tests / fast path)."""
    return _execute_instrument(instrument_name, inputs_dict, assumptions)


def envelope_to_result(envelope: Envelope, *, instrument_name: str) -> InstrumentResult:
    """Deserialize a child envelope — re-raises ``ValueError`` for instrument input errors."""
    if envelope.get("ok"):
        payload = envelope.get("result")
        if not isinstance(payload, dict):
            msg = "Child returned a malformed success envelope"
            raise ValueError(msg)
        return InstrumentResult.model_validate(payload)

    error = envelope.get("error")
    kind = envelope.get("kind")
    message = error if isinstance(error, str) else "Child process failed"
    if kind == "value_error":
        raise ValueError(message)
    from app.toolbench.execution.errors import ToolbenchMemoryExceeded, ToolbenchWorkerError

    if kind == "memory":
        raise ToolbenchMemoryExceeded(instrument_name=instrument_name, message=message)
    raise ToolbenchWorkerError(instrument_name=instrument_name, message=message)


def child_exit_implies_memory_kill(exit_code: int | None) -> bool:
    """Whether a negative exit code indicates SIGKILL (timeout kill or OOM)."""
    return exit_code is not None and exit_code < 0 and -exit_code == signal.SIGKILL