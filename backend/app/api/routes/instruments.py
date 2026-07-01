"""The human-invokable toolbench API surface (Phase 6) — catalog + run.

Two endpoints, mirroring existing patterns exactly:

- ``GET /instruments`` — the public, read-only instrument catalog, the ``GET /agent-models/catalog``
  pattern: static reference data served from the Phase-2 serializer over the *code* registry, so it
  can never advertise an instrument the runtime lacks. No auth (the catalog is public).
- ``POST /projects/{id}/instruments/{name}/run`` — resolve the instrument from the registry (this is
  where the 404-on-unknown-name lives, per the Phase-3 split), gate to project membership, and hand
  off to ``services/tool_runs.run_instrument`` — the same chokepoint-composed write an agent will
  later drive through this identical API.

The same surface serves humans now and agents later; there is no parallel path.
"""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.api.deps import ActingActor, DbSession
from app.schemas.instrument import InstrumentDescriptor
from app.schemas.tool_run import ToolRunRequest, ToolRunResult
from app.services import tool_runs
from app.services.project_members import ensure_is_member
from app.toolbench import build_catalog, registry

router = APIRouter()


@router.get("/instruments", response_model=list[InstrumentDescriptor], tags=["instruments"])
async def list_instruments() -> list[InstrumentDescriptor]:
    """The public instrument catalog: name, schemas, and the three-outcome result contract.

    Public (no auth) static reference data, like ``GET /agent-models/catalog`` — cacheable
    indefinitely. Reflects the code registry, so the menu is always in lock-step with what runs.
    """
    return build_catalog()


@router.post(
    "/projects/{project_id}/instruments/{name}/run",
    response_model=ToolRunResult,
    status_code=status.HTTP_201_CREATED,
    tags=["instruments"],
)
async def run_instrument(
    project_id: UUID,
    name: str,
    payload: ToolRunRequest,
    db: DbSession,
    actor: ActingActor,
) -> ToolRunResult:
    """Run instrument ``name`` in a project and land the result in the ledger, atomically.

    Order: authenticate (the ``ActingActor`` dependency → ``401``), resolve the instrument (``404``
    on an unknown name — the registry owns this, keeping the service registry-agnostic), authorize
    project membership (``404`` missing project / ``403`` non-member), then compose the run through
    the checkpoint chokepoint. A bad ``inputs`` payload (mismatching the instrument's
    ``InputModel``) surfaces as ``422`` from the service; a tool that fails to run is ``422`` and
    mints nothing.
    """
    instrument = registry.get(name)
    if instrument is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown instrument {name!r}"
        )

    await ensure_is_member(db, project_id, actor)

    return await tool_runs.run_instrument(
        db,
        project_id,
        instrument,
        actor,
        inputs=payload.inputs,
        assumptions=payload.assumptions,
        thread_id=payload.thread_id,
        claim_id=payload.claim_id,
        relation_kind=payload.relation_kind,
    )
