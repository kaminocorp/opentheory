"""The maths toolbench — deterministic research instruments and the contract they conform to.

Phase 2 shipped the *shape*: the :class:`Instrument` adapter protocol, the code
:class:`InstrumentRegistry` (single source of truth), the catalog serializer, and the conformance
checker. Phase 4 adds the first real instruments — importing the ``instruments`` subpackage (the
side-effect import below) registers them into :data:`registry`, so any import of ``app.toolbench``
yields a populated registry (what the conformance auto-coverage test and Phase 6's endpoints rely
on). Import order within this block is irrelevant: the instrument modules import their own
dependencies (``adapter`` / ``registry``) directly, so there is no cycle.
"""

# Side-effect import: registers the Tier-0 instruments into ``registry``.
from app.toolbench import instruments
from app.toolbench.adapter import Instrument, InstrumentResult
from app.toolbench.catalog import RESULT_CONTRACT, build_catalog, describe
from app.toolbench.conformance import check_conformance
from app.toolbench.registry import InstrumentRegistry, registry

__all__ = [
    "RESULT_CONTRACT",
    "Instrument",
    "InstrumentRegistry",
    "InstrumentResult",
    "build_catalog",
    "check_conformance",
    "describe",
    "instruments",
    "registry",
]
