"""Registry → catalog serializer: turn each registered instrument into a read-only descriptor.

This is what the human UI and (later) the agent API consume. It reflects the *code* registry, so the
catalog can never offer an instrument the runtime doesn't actually have.
"""

from app.models.enums import ResultStatus
from app.schemas.instrument import InstrumentDescriptor, ResultContractOutcome
from app.toolbench.adapter import Instrument
from app.toolbench.registry import InstrumentRegistry
from app.toolbench.registry import registry as _default_registry

# The universal three-outcome contract, surfaced on every descriptor (see ResultContractOutcome).
RESULT_CONTRACT: tuple[ResultContractOutcome, ...] = (
    ResultContractOutcome(
        status=ResultStatus.RESULT,
        meaning="The instrument ran and produced a result.",
    ),
    ResultContractOutcome(
        status=ResultStatus.REFUTED,
        meaning="The instrument ran and falsified the claim — a counterexample (definitive).",
    ),
    ResultContractOutcome(
        status=ResultStatus.UNDECIDED,
        meaning="The instrument ran but could not decide — escalate to a proof; never a pass.",
    ),
)


def describe(instrument: Instrument) -> InstrumentDescriptor:
    """Serialize a single instrument to its catalog descriptor (input/output as JSON Schema)."""
    return InstrumentDescriptor(
        name=instrument.name,
        namespace=instrument.namespace,
        version=instrument.version,
        engine=instrument.engine,
        engine_version=instrument.engine_version,
        description=instrument.description,
        input_schema=instrument.InputModel.model_json_schema(),
        output_schema=instrument.OutputModel.model_json_schema(),
        result_contract=list(RESULT_CONTRACT),
    )


def build_catalog(registry: InstrumentRegistry | None = None) -> list[InstrumentDescriptor]:
    """The full catalog for a registry (defaults to the production one), ordered by name."""
    reg = registry if registry is not None else _default_registry
    return [describe(instrument) for instrument in reg.all()]
