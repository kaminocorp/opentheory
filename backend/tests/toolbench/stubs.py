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


def register_test_instruments() -> None:
    if "test.sleep" not in registry:
        registry.register(_SLEEP)
    if "test.blob" not in registry:
        registry.register(_BLOB)


__all__ = ["BlobInstrument", "SleepInstrument", "register_test_instruments"]