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


_SLEEP = SleepInstrument()
_BLOB = BlobInstrument()


class WritePathStubInput(BaseModel):
    value: int


class WritePathStubOutput(BaseModel):
    value: int


class WritePathStub:
    """Write-path composition stub. Registered under ``test.stub*`` so the sandbox
    worker cannot confuse it with production ``calc.eval`` (which requires
    ``expression`` and has run through the worker since 0.11.3).
    """

    namespace = "test"
    version = "0.1.0"
    engine = "builtin"
    engine_version = "1.0"
    description = "Write-path composition stub (not a production instrument)."
    InputModel = WritePathStubInput
    OutputModel = WritePathStubOutput

    def __init__(
        self,
        name: str,
        *,
        status: ResultStatus = ResultStatus.RESULT,
        artifact_kind: str = "derivation",
        raises: bool = False,
    ) -> None:
        if not name.startswith("test."):
            raise ValueError("write-path stubs must use a test.* name, not a production instrument")
        self.name = name
        self._status = status
        self._kind = artifact_kind
        self._raises = raises

    def run(self, inputs: WritePathStubInput, assumptions: dict[str, Any]) -> InstrumentResult:
        if self._raises:
            raise RuntimeError("engine exploded")
        return InstrumentResult(
            output={"value": inputs.value},
            status=self._status,
            artifact_kind=self._kind,
        )


WRITE_PATH_STUB = WritePathStub("test.stub")
WRITE_PATH_STUB_REFUTED = WritePathStub(
    "test.stub_refuted",
    status=ResultStatus.REFUTED,
    artifact_kind="counterexample",
)
WRITE_PATH_STUB_UNDECIDED = WritePathStub("test.stub_undecided", status=ResultStatus.UNDECIDED)
WRITE_PATH_STUB_BOOM = WritePathStub("test.stub_boom", raises=True)

_WRITE_PATH_STUBS = (
    WRITE_PATH_STUB,
    WRITE_PATH_STUB_REFUTED,
    WRITE_PATH_STUB_UNDECIDED,
    WRITE_PATH_STUB_BOOM,
)


def register_test_instruments() -> None:
    if "test.sleep" not in registry:
        registry.register(_SLEEP)
    if "test.blob" not in registry:
        registry.register(_BLOB)
    for stub in _WRITE_PATH_STUBS:
        if stub.name not in registry:
            registry.register(stub)


__all__ = [
    "BlobInstrument",
    "SleepInstrument",
    "WRITE_PATH_STUB",
    "WRITE_PATH_STUB_BOOM",
    "WRITE_PATH_STUB_REFUTED",
    "WRITE_PATH_STUB_UNDECIDED",
    "WritePathStub",
    "register_test_instruments",
]