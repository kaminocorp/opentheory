"""Test-only toolbench instruments — never registered in production imports.

``register_test_instruments`` is called from the subprocess worker when pytest is on
``PYTHONPATH``, so spawn children can resolve ``test.*`` instrument names.
"""

import time
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import ResultStatus
from app.toolbench.adapter import InstrumentResult
from app.toolbench.registry import registry


class SleepInput(BaseModel):
    seconds: float = Field(gt=0, le=60)


class SleepOutput(BaseModel):
    slept: float


class SleepInstrument:
    """Sleeps for ``seconds`` — used to prove wall-clock timeout in the subprocess runner."""

    name = "test.sleep"
    namespace = "test"
    version = "0.0.0"
    engine = "builtin"
    engine_version = "1.0"
    description = "Test stub that sleeps (not a production instrument)."
    InputModel = SleepInput
    OutputModel = SleepOutput

    def run(self, inputs: SleepInput, assumptions: dict[str, Any]) -> InstrumentResult:
        time.sleep(inputs.seconds)
        return InstrumentResult(
            output={"slept": inputs.seconds},
            status=ResultStatus.RESULT,
            artifact_kind="derivation",
        )


class BlobInput(BaseModel):
    size: int = Field(gt=0, le=5_000_000)


class BlobOutput(BaseModel):
    size: int
    blob: str


class BlobInstrument:
    """Returns a ``size``-byte output — used to prove a result larger than the OS pipe buffer
    drains without wedging the child (which a join-before-read runner misreads as a timeout)."""

    name = "test.blob"
    namespace = "test"
    version = "0.0.0"
    engine = "builtin"
    engine_version = "1.0"
    description = "Test stub that returns a large output blob (not a production instrument)."
    InputModel = BlobInput
    OutputModel = BlobOutput

    def run(self, inputs: BlobInput, assumptions: dict[str, Any]) -> InstrumentResult:
        return InstrumentResult(
            output={"size": inputs.size, "blob": "x" * inputs.size},
            status=ResultStatus.RESULT,
            artifact_kind="derivation",
        )


class WritePathInput(BaseModel):
    value: int


class WritePathOutput(BaseModel):
    value: int


class WritePathInstrument:
    """In-process / spawn-safe stub for ``test_write_path`` ledger mechanics.

    The sandbox worker looks instruments up by name (never pickles the caller's
    object). Naming a stub ``calc.eval`` therefore runs the *real* instrument.
    These ``test.write*`` names stay off the production catalog.
    """

    namespace = "test"
    version = "0.1.0"
    engine = "sympy"
    engine_version = "1.13.2"
    description = "Write-path stub (not a production instrument)."
    InputModel = WritePathInput
    OutputModel = WritePathOutput

    def __init__(
        self,
        name: str,
        *,
        status: ResultStatus = ResultStatus.RESULT,
        artifact_kind: str = "derivation",
        raises: bool = False,
    ) -> None:
        self.name = name
        self._status = status
        self._kind = artifact_kind
        self._raises = raises

    def run(self, inputs: WritePathInput, assumptions: dict[str, Any]) -> InstrumentResult:
        if self._raises:
            raise RuntimeError("engine exploded")
        return InstrumentResult(
            output={"value": inputs.value},
            status=self._status,
            artifact_kind=self._kind,
        )


_SLEEP = SleepInstrument()
_BLOB = BlobInstrument()
WRITE = WritePathInstrument("test.write")
WRITE_REFUTE = WritePathInstrument(
    "test.write_refute",
    status=ResultStatus.REFUTED,
    artifact_kind="counterexample",
)
WRITE_UNDECIDED = WritePathInstrument(
    "test.write_undecided",
    status=ResultStatus.UNDECIDED,
)
WRITE_BOOM = WritePathInstrument("test.write_boom", raises=True)


def register_test_instruments() -> None:
    if "test.sleep" not in registry:
        registry.register(_SLEEP)
    if "test.blob" not in registry:
        registry.register(_BLOB)
    if "test.write" not in registry:
        registry.register(WRITE)
    if "test.write_refute" not in registry:
        registry.register(WRITE_REFUTE)
    if "test.write_undecided" not in registry:
        registry.register(WRITE_UNDECIDED)
    if "test.write_boom" not in registry:
        registry.register(WRITE_BOOM)


__all__ = [
    "BlobInstrument",
    "SleepInstrument",
    "WRITE",
    "WRITE_BOOM",
    "WRITE_REFUTE",
    "WRITE_UNDECIDED",
    "WritePathInstrument",
    "register_test_instruments",
]