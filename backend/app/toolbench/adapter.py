"""The toolbench adapter interface — the single shape every instrument conforms to.

This is *the real build object* of the toolbench (plan Decision 7): ``calc.eval`` /
``expr.compare`` / ``oeis.search`` / ``geometry.coordinate_measure`` are its first conformance
tests, not the point. An instrument takes typed inputs, runs deterministically under an assumption
set, and returns an :class:`InstrumentResult` carrying one of the **three honest outcomes**
(``result`` / ``refuted`` / ``undecided``) — the status is *returned*, never inferred.

Defined as a :class:`typing.Protocol` (structural typing): an instrument is *anything* with these
attributes and this ``run`` — no base class to inherit, so a plain object or a dataclass qualifies.
``@runtime_checkable`` lets the registry reject a non-conforming object at registration time.
"""

from collections.abc import Awaitable
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ResultStatus


class InstrumentResult(BaseModel):
    """What every instrument's ``run`` returns.

    ``status`` is one of the three honest outcomes and is decided by the instrument, not inferred
    by the caller. ``artifact_kind`` names the kind of ``Artifact`` this run produces —
    ``derivation`` / ``counterexample`` / ``measurement`` / ``pinned_source``. It lives on the
    *result*, not the instrument, because one instrument can yield different kinds per run (e.g.
    ``expr.compare`` yields a ``derivation`` when equivalent but a ``counterexample`` when refuted).
    ``output`` is
    free-form here but is expected to validate against the instrument's ``OutputModel`` (the
    conformance harness checks exactly that).

    ``source_type`` lets a *retrieval* instrument mark the ``Evidence`` it produces as externally
    sourced (e.g. ``"oeis"``) rather than the default ``"tool"``; the compute instruments leave it
    ``None`` (the write path falls back to ``"tool"``). It is a provenance hint about *where* the
    result came from, not a new credit axis.
    """

    model_config = ConfigDict(extra="forbid")

    output: dict[str, Any]
    status: ResultStatus
    artifact_kind: str = Field(min_length=1)
    source_type: str | None = None


@runtime_checkable
class Instrument(Protocol):
    """The structural contract a toolbench instrument satisfies.

    Attribute meanings map onto the blame tuple (``ToolInvocation``) the write path records:
    ``version`` → ``instrument_version``, ``engine`` / ``engine_version`` pinned for reproduction.
    ``InputModel`` / ``OutputModel`` both validate values *and* self-describe as JSON Schema for the
    catalog. ``name`` is the fully-qualified ``namespace.verb`` (e.g. ``expr.compare``);
    ``namespace`` is its leading segment.
    """

    name: str
    namespace: str
    version: str
    engine: str
    engine_version: str
    description: str
    InputModel: type[BaseModel]
    OutputModel: type[BaseModel]

    def run(
        self, inputs: BaseModel, assumptions: dict[str, Any]
    ) -> InstrumentResult | Awaitable[InstrumentResult]:
        """Run on already-validated ``inputs`` under ``assumptions`` → an :class:`InstrumentResult`.

        ``inputs`` is an instance of ``InputModel`` (the caller validates the raw dict first). A
        tool *exception* means it did not run — the write path records no result for it; a genuine
        ``undecided`` is a successful run and *is* recorded.

        Compute instruments are pure and **synchronous**. A *retrieval* instrument (Phase 5, e.g.
        ``oeis.search``) hits an external source and stamps a real-time ``retrieved_at``, so it is
        not a pure function of its inputs; such an instrument may implement ``run`` as ``async def``
        and return an awaitable. The write path awaits the result when it is awaitable, so both
        shapes compose through the same chokepoint. The conformance harness behaviourally checks
        only the synchronous shape (an awaitable ``run`` is structurally checked instead).
        """
        ...
