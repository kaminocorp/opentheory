"""Tool-run write path — turn *"run instrument X with inputs Y in project P"* into a ledger result.

One service function, :func:`run_instrument`, composes a single deterministic instrument run into an
``Artifact`` (the product), an optional ``Evidence`` (+ its claim/artifact links) when the run
targets a ``Claim``, and a ``Checkpoint`` carrying the **blame tuple** — all through the checkpoint
chokepoint, in **one transaction**, attributed to the acting actor as a ``tool_run`` contribution.

Two invariants this file must never break (the plan's top review checks):

- **Atomicity via the chokepoint.** We ``db.add`` the artifact/evidence/link rows and **never
  commit**; ``create_checkpoint`` owns the single commit. A stray commit here — or minting a
  ``Checkpoint`` outside the chokepoint — would break the one-transaction guarantee and could orphan
  an artifact.
- **The failure split.** A tool *exception* means the instrument **did not run**: we mint nothing
  and surface a ``4xx``. Crucially, ``run`` executes *before* any ``db.add``, so a failure there
  leaves the session untouched. A genuine ``undecided`` is a *successful* run and **is** recorded —
  a real, citable outcome, never an error.
"""

import hashlib
import json
from inspect import isawaitable, iscoroutinefunction
from typing import Any
from uuid import UUID

import anyio
from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.actor import Actor
from app.models.artifact import Artifact
from app.models.claim import Claim
from app.models.enums import ResultStatus
from app.models.evidence import Evidence
from app.models.links import ClaimEvidenceLink, EvidenceArtifactLink
from app.models.thread import Thread
from app.schemas.checkpoint import CheckpointCreate, CheckpointRefInput
from app.schemas.tool_invocation import ToolInvocation
from app.schemas.tool_run import ToolRunResult
from app.services import checkpoints as checkpoint_service
from app.services import contributions
from app.services.evidence import RELATION_KINDS
from app.toolbench.adapter import Instrument

# When the caller does not pin a relation_kind, derive a sensible default from the honest outcome:
# a counterexample weakens; a result supports; a couldn't-decide is context (never support/weaken).
_STATUS_RELATION_DEFAULT: dict[ResultStatus, str] = {
    ResultStatus.RESULT: "support",
    ResultStatus.REFUTED: "weaken",
    ResultStatus.UNDECIDED: "context",
}

# The evidence↔artifact link role a tool run records (a plain VARCHAR, validated here).
_EVIDENCE_FROM_ARTIFACT = "derived_from"


def _canonical_output_hash(output: dict[str, Any]) -> str:
    """A stable content hash of the result output (canonical JSON → sha256).

    v1 instruments produce exact/symbolic/string outputs, so JSON-hashing is reproducible. Never
    feed a bare float through here and treat it as an exact hash — numeric instruments (Phase 4/5)
    must canonicalise first (``srepr`` / a pinned tolerance), per the maths-toolbox
    float-reproducibility caveat.
    """
    canonical = json.dumps(output, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def run_instrument(
    db: AsyncSession,
    project_id: UUID,
    instrument: Instrument,
    actor: Actor,
    *,
    inputs: dict[str, Any],
    assumptions: dict[str, Any] | None = None,
    thread_id: UUID | None = None,
    branch_id: UUID | None = None,
    claim_id: UUID | None = None,
    relation_kind: str | None = None,
) -> ToolRunResult:
    """Run ``instrument`` in ``project_id`` and land the result in the ledger, atomically.

    The caller (the Phase 6 route) resolves ``instrument`` from the registry (and owns the 404 on an
    unknown name), so this service takes the resolved object and stays decoupled from the registry.
    ``inputs`` is the raw client dict (validated here against ``instrument.InputModel``);
    ``assumptions`` is recorded on the produced rows and in the blame tuple. When ``claim_id`` is
    given, the result is also minted as ``Evidence`` linked to that claim (``relation_kind``
    defaults from the outcome). ``branch_id`` records the produced checkpoint on a branch (validated
    — project match + still open — by the chokepoint); ``None`` records on the project main line.
    """
    assumptions = assumptions or {}

    # ``relation_kind`` labels the claim↔evidence link, so it is meaningless without a claim;
    # passing it alone is a caller mistake, not a silent no-op.
    if relation_kind is not None and claim_id is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "relation_kind requires a claim_id"
        )

    # Validate the target claim up front (fail fast, mint nothing) when the run targets one.
    claim: Claim | None = None
    if claim_id is not None:
        claim = await db.get(Claim, claim_id)
        if claim is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Claim not found")
        if claim.project_id != project_id:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Claim belongs to a different project"
            )
        # A claim carries its own thread, and the result lands on it (``effective_thread_id``
        # below). Silently ignoring a conflicting ``thread_id`` would mislead the caller about
        # where the result went, so a mismatch is a 422 (a matching ``thread_id`` is harmless).
        if thread_id is not None and thread_id != claim.thread_id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "thread_id conflicts with the claim's thread; omit it or pass the claim's thread",
            )
        if relation_kind is not None and relation_kind not in RELATION_KINDS:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"relation_kind must be one of {sorted(RELATION_KINDS)}",
            )
    # A free-standing thread target must be validated up front too, for the same reason the claim
    # is: the artifact is flushed with this ``thread_id`` *before* the chokepoint validates it (step
    # 6), so an unknown/foreign id would otherwise surface as a 500 (FK violation at the flush)
    # instead of a clean 4xx. (When a claim is given, the thread is the claim's own — validated
    # above — so this only guards the no-claim path, which is exactly when ``thread_id`` is used.)
    elif thread_id is not None:
        thread = await db.get(Thread, thread_id)
        if thread is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Thread not found")
        if thread.project_id != project_id:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Thread belongs to a different project"
            )

    # 1. Validate the inputs against the instrument's declared InputModel.
    try:
        validated = instrument.InputModel.model_validate(inputs)
    except ValidationError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Invalid inputs for {instrument.name}: {exc}",
        ) from exc

    # 2. Run. A tool exception means it did not run: mint nothing, surface a 4xx. This is before
    #    any db.add, so the session is untouched (no rollback needed). A compute instrument's
    #    ``run`` is synchronous and CPU-bound; run it in a worker thread so a slow expression cannot
    #    block the event loop and freeze every concurrent request on this worker. A retrieval
    #    instrument's ``run`` is async (it hits the network); await it directly. Either way the
    #    await precedes any db.add, so a network/compute failure mints nothing too.
    try:
        if iscoroutinefunction(instrument.run):
            result = await instrument.run(validated, assumptions)
        else:
            result = await anyio.to_thread.run_sync(instrument.run, validated, assumptions)
            if isawaitable(result):  # a sync run that returned an awaitable — await it on the loop
                result = await result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Instrument {instrument.name} failed to run: {exc}",
        ) from exc

    content_hash = _canonical_output_hash(result.output)
    # Evidence/artifact/checkpoint all sit on the claim's thread when targeting a claim.
    effective_thread_id = claim.thread_id if claim is not None else thread_id

    # 3. The Artifact — the product of the run. Added, not committed.
    artifact = Artifact(
        project_id=project_id,
        thread_id=effective_thread_id,
        name=f"{instrument.name} → {result.status.value}",
        kind=result.artifact_kind,
        content_hash=content_hash,
        assumptions=assumptions,
        artifact_metadata={"output": result.output, "status": result.status.value},
    )
    db.add(artifact)
    await db.flush()  # assign artifact.id for the blame tuple + refs

    # Service-supplied (trusted) refs: the checkpoint points at what it produced/recorded.
    extra_refs = [
        CheckpointRefInput(target_type="artifact", target_id=artifact.id, role="produced")
    ]

    # 4. Optional Evidence against a claim, plus the claim↔evidence and evidence↔artifact links.
    evidence_id: UUID | None = None
    if claim is not None:
        rel = relation_kind or _STATUS_RELATION_DEFAULT[result.status]
        evidence = Evidence(
            project_id=claim.project_id,
            thread_id=claim.thread_id,
            title=f"{instrument.name} → {result.status.value}"[:240],
            # A retrieval instrument marks its evidence as externally sourced (e.g. "oeis");
            # compute instruments leave it None → the generic "tool".
            source_type=result.source_type or "tool",
            content_hash=content_hash,
            assumptions=assumptions,
            evidence_metadata={
                "output": result.output,
                "status": result.status.value,
                "instrument": instrument.name,
            },
        )
        db.add(evidence)
        await db.flush()  # assign evidence.id for the links + ref
        db.add(
            ClaimEvidenceLink(claim_id=claim.id, evidence_id=evidence.id, relation_kind=rel)
        )
        db.add(
            EvidenceArtifactLink(
                evidence_id=evidence.id,
                artifact_id=artifact.id,
                role=_EVIDENCE_FROM_ARTIFACT,
            )
        )
        extra_refs.append(
            CheckpointRefInput(target_type="evidence", target_id=evidence.id, role="recorded")
        )
        extra_refs.append(
            CheckpointRefInput(target_type="claim", target_id=claim.id, role="evidenced")
        )
        evidence_id = evidence.id

    # 5. The blame tuple — the irreversible provenance fact, stamped with the artifact it produced.
    invocation = ToolInvocation(
        instrument=instrument.name,
        instrument_version=instrument.version,
        engine=instrument.engine,
        engine_version=instrument.engine_version,
        inputs=validated.model_dump(mode="json"),
        output=result.output,
        assumptions=assumptions,
        status=result.status,
        produced_artifact_id=artifact.id,
    )

    # 6. Compose through the chokepoint — it owns the single commit, so artifact + evidence + links
    #    + checkpoint + refs + the tool_run contribution all persist (or roll back) atomically.
    checkpoint = await checkpoint_service.create_checkpoint(
        db,
        project_id,
        CheckpointCreate(
            thread_id=effective_thread_id,
            branch_id=branch_id,
            summary=f"Ran {instrument.name} → {result.status.value}",
            content={"instrument": instrument.name, "status": result.status.value},
        ),
        actor,
        extra_refs=extra_refs,
        tool_invocations=[invocation],
        contribution_action=contributions.ACTION_TOOL_RUN,
    )

    return ToolRunResult(
        checkpoint=checkpoint,
        artifact_id=artifact.id,
        evidence_id=evidence_id,
        status=result.status,
        content_hash=content_hash,
    )
