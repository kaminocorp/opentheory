"""The conformance checker — the contract's *executable* definition.

``check_conformance`` returns a list of human-readable problems (empty ⇒ conforms), so it is usable
from a test (``assert check_conformance(...) == []``) *and* from any non-test caller without a
pytest dependency. It lives in production code (not the test tree) so Phase 4's per-instrument tests
import it directly; each new instrument is "one conformance test against Phase 2".

Two layers of check:

- **structural** (always) — the metadata attributes, the Pydantic models, and JSON-schema-ability;
- **behavioural** (only when ``example_inputs`` is supplied) — that ``run`` executes on validated
  inputs, returns an :class:`InstrumentResult`, and that its ``output`` actually validates against
  the instrument's declared ``OutputModel`` (which Pydantic does *not* enforce on its own, since
  ``InstrumentResult.output`` is a free-form dict).
"""

from inspect import isawaitable
from typing import Any

from pydantic import BaseModel, ValidationError

from app.toolbench.adapter import Instrument, InstrumentResult

_REQUIRED_STR_ATTRS = ("name", "namespace", "version", "engine", "engine_version", "description")


def _is_basemodel(obj: Any) -> bool:
    return isinstance(obj, type) and issubclass(obj, BaseModel)


def check_conformance(
    instrument: Instrument,
    *,
    example_inputs: dict[str, Any] | None = None,
    assumptions: dict[str, Any] | None = None,
) -> list[str]:
    """Return the ways ``instrument`` violates the adapter contract (empty list ⇒ conforms)."""
    problems: list[str] = []

    for attr in _REQUIRED_STR_ATTRS:
        value = getattr(instrument, attr, None)
        if not isinstance(value, str) or not value.strip():
            problems.append(f"{attr!r} must be a non-empty string (got {value!r})")

    # name must be the fully-qualified "namespace.verb".
    name = getattr(instrument, "name", "")
    namespace = getattr(instrument, "namespace", "")
    if isinstance(name, str) and name and isinstance(namespace, str) and namespace:
        if "." not in name or name.split(".", 1)[0] != namespace:
            problems.append(
                f"name {name!r} must be '{namespace}.<verb>' for namespace {namespace!r}"
            )

    input_model = getattr(instrument, "InputModel", None)
    output_model = getattr(instrument, "OutputModel", None)
    for label, model in (("InputModel", input_model), ("OutputModel", output_model)):
        if not _is_basemodel(model):
            problems.append(f"{label} must be a pydantic BaseModel subclass (got {model!r})")
        else:
            # A model that can't emit JSON Schema can't populate the catalog.
            try:
                if not isinstance(model.model_json_schema(), dict):
                    problems.append(f"{label}.model_json_schema() did not return a dict")
            except Exception as exc:  # surfaced as a problem, never raised
                problems.append(f"{label}.model_json_schema() raised: {exc!r}")

    if not callable(getattr(instrument, "run", None)):
        problems.append("run must be callable")
        return problems  # nothing further is exercisable

    if example_inputs is None or not _is_basemodel(input_model):
        return problems  # structural-only pass

    # Behavioural pass: exercise run() the way the write path will (validate inputs first).
    try:
        validated = input_model.model_validate(example_inputs)
    except ValidationError as exc:
        problems.append(f"example_inputs did not validate against InputModel: {exc}")
        return problems

    try:
        result = instrument.run(validated, assumptions or {})
    except Exception as exc:  # a raising run is a conformance failure, not a crash
        problems.append(f"run() raised on example_inputs: {exc!r}")
        return problems

    # A retrieval instrument's ``run`` is async (Phase 5). We cannot await it here without an event
    # loop (and would not want the network I/O in a conformance check), so behavioural checking is
    # structural-only for async instruments — their output is verified in a dedicated async test.
    # Close the un-awaited coroutine so it does not raise a "never awaited" warning.
    if isawaitable(result):
        result.close()
        return problems

    if not isinstance(result, InstrumentResult):
        problems.append(f"run() must return an InstrumentResult (got {type(result)!r})")
        return problems

    if _is_basemodel(output_model):
        try:
            output_model.model_validate(result.output)
        except ValidationError as exc:
            problems.append(f"run() output does not conform to OutputModel: {exc}")

    return problems
