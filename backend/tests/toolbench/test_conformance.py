"""Phase 2 — adapter interface, registry, catalog serializer, conformance harness.

Pure in-process (no DB). Proves the machinery with a **toy fixture instrument** (``demo.echo``, a
test-only object, never registered into production) and asserts the production registry is
empty-but-valid. Phase 4's real instruments each reuse ``check_conformance`` as their own test.

See ``docs/executing/toolbench-provenance-and-first-instruments.md`` Phase 2.
"""

from typing import Any

import pytest
from pydantic import BaseModel

from app.models.enums import ResultStatus
from app.schemas.instrument import InstrumentDescriptor
from app.toolbench.adapter import Instrument, InstrumentResult
from app.toolbench.catalog import build_catalog
from app.toolbench.conformance import check_conformance
from app.toolbench.registry import InstrumentRegistry, registry

# --- a toy conforming instrument (test fixture only — NOT a production instrument) ----------------


class _EchoInputs(BaseModel):
    value: int


class _EchoOutput(BaseModel):
    value: int


class EchoInstrument:
    """Echoes its integer input — the minimal object that satisfies the Instrument protocol."""

    name = "demo.echo"
    namespace = "demo"
    version = "0.0.0"
    engine = "builtin"
    engine_version = "1.0"
    description = "Echoes its integer input back (a conformance fixture, not a real instrument)."
    InputModel = _EchoInputs
    OutputModel = _EchoOutput

    def run(self, inputs: _EchoInputs, assumptions: dict[str, Any]) -> InstrumentResult:
        return InstrumentResult(
            output={"value": inputs.value},
            status=ResultStatus.RESULT,
            artifact_kind="derivation",
        )


TOY = EchoInstrument()
TOY_INPUTS = {"value": 42}


# --- the adapter contract -------------------------------------------------------------------------


def test_toy_satisfies_instrument_protocol() -> None:
    assert isinstance(TOY, Instrument)


def test_toy_conforms_including_run() -> None:
    assert check_conformance(TOY, example_inputs=TOY_INPUTS) == []


def test_check_conformance_flags_structural_violations() -> None:
    class Broken:
        name = "broken"  # not a "namespace.verb"
        namespace = ""  # blank
        version = ""
        engine = ""
        engine_version = ""
        description = ""
        InputModel = None  # not a BaseModel
        OutputModel = None

    problems = check_conformance(Broken())  # type: ignore[arg-type]
    assert problems
    assert any("InputModel" in p for p in problems)
    assert any("namespace" in p for p in problems)


def test_check_conformance_flags_output_not_matching_output_model() -> None:
    class Liar(EchoInstrument):
        name = "demo.liar"
        namespace = "demo"

        def run(self, inputs: _EchoInputs, assumptions: dict[str, Any]) -> InstrumentResult:
            # Declares _EchoOutput{value:int} but returns a string — the harness must catch it.
            return InstrumentResult(
                output={"value": "not-an-int"},
                status=ResultStatus.RESULT,
                artifact_kind="derivation",
            )

    problems = check_conformance(Liar(), example_inputs=TOY_INPUTS)
    assert any("OutputModel" in p for p in problems)


# --- the registry ---------------------------------------------------------------------------------


def test_production_registry_holds_the_tier0_instruments() -> None:
    # Empty-but-valid in Phase 2; Phase 4 registers the first real instruments (importing
    # ``app.toolbench`` populates the registry). The auto-coverage test below now conformance-checks
    # each of them; here we just assert they are present and the catalog reflects them 1:1.
    assert isinstance(registry, InstrumentRegistry)
    names = {i.name for i in registry.all()}
    assert {
        "calc.eval",
        "expr.compare",
        "geometry.coordinate_measure",
        "oeis.search",
    } <= names
    catalog = build_catalog()
    assert len(catalog) == len(registry)
    assert all(isinstance(d, InstrumentDescriptor) for d in catalog)


def test_registry_register_get_and_reject_duplicate() -> None:
    reg = InstrumentRegistry()
    reg.register(TOY)
    assert len(reg) == 1
    assert reg.get("demo.echo") is TOY
    assert "demo.echo" in reg
    assert reg.all() == [TOY]
    with pytest.raises(ValueError):
        reg.register(TOY)  # duplicate name


def test_registry_rejects_nonconforming_object() -> None:
    reg = InstrumentRegistry()

    class NotAnInstrument:
        name = "x.y"  # has a name but none of the rest

    with pytest.raises(TypeError):
        reg.register(NotAnInstrument())  # type: ignore[arg-type]


def test_registry_all_is_name_ordered() -> None:
    reg = InstrumentRegistry()

    class Second(EchoInstrument):
        name = "demo.zulu"

    class First(EchoInstrument):
        name = "demo.alpha"

    reg.register(Second())
    reg.register(First())
    assert [i.name for i in reg.all()] == ["demo.alpha", "demo.zulu"]


# --- the catalog serializer -----------------------------------------------------------------------


def test_catalog_serializes_instrument_to_json_schema() -> None:
    reg = InstrumentRegistry()
    reg.register(TOY)

    catalog = build_catalog(reg)
    assert len(catalog) == 1
    descriptor = catalog[0]
    assert isinstance(descriptor, InstrumentDescriptor)
    assert descriptor.name == "demo.echo"
    assert descriptor.namespace == "demo"
    assert descriptor.engine == "builtin"

    # input/output are real JSON Schema derived from the Pydantic models.
    assert descriptor.input_schema["type"] == "object"
    assert "value" in descriptor.input_schema["properties"]
    assert descriptor.output_schema["properties"]["value"]["type"] == "integer"

    # the universal three-outcome contract rides on every descriptor.
    statuses = {outcome.status for outcome in descriptor.result_contract}
    assert statuses == {ResultStatus.RESULT, ResultStatus.REFUTED, ResultStatus.UNDECIDED}


# --- auto-coverage wiring for Phase 4+ ------------------------------------------------------------

# Parametrized over the *production* registry so every real instrument is structurally
# conformance-checked the moment it is registered. Empty in Phase 2 (a single designed skip); from
# Phase 4 on it runs once per registered instrument (calc.eval / expr.compare / geometry.*).
@pytest.mark.parametrize("instrument", registry.all(), ids=lambda i: i.name)
def test_registered_instruments_are_structurally_conformant(instrument: Instrument) -> None:
    assert check_conformance(instrument) == []
