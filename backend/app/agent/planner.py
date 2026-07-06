"""The planner (0.12.1) — (thread + open claims + catalog) → a validated, bounded plan.

The one place an LLM decides anything in the loop. It is deliberately **pure and injectable**: it
takes an ``llm`` (the :class:`~app.agent.llm.LlmClient` protocol — a ``StubLlm`` in tests) and does
**no** database writes, so it is fully testable with a canned model response and no network/DB.

Two-stage validation is the safety spine (mirroring ``run_instrument``'s own guards, applied
*before* execution so a bad step mints nothing):

1. **Structural** — the model's text is parsed as JSON and validated against :class:`AgentPlan`.
   A non-JSON or schema-invalid body is an :class:`~app.agent.llm.AgentLlmError` (the orchestrator
   records it and mints nothing) — the whole pass fails legibly, never a ``500``.
2. **Semantic, per run** — each proposed run is dropped (never raised) with a recorded reason when
   its instrument is unknown, its ``inputs`` fail the instrument's ``InputModel``, its ``claim_id``
   is not one of the open claims, or a ``relation_kind`` is malformed / lacks a ``claim_id``. The
   runnable remainder is then truncated to ``max_runs`` (the per-pass safety cap), each excess run
   recorded as dropped. So the orchestrator only ever executes runnable, pre-validated steps.

An *empty* plan ("nothing to do") is a valid, error-free outcome (0 runnable, 0 dropped).
"""

import json
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.agent.llm import AgentLlmError, LlmClient
from app.agent.prompts import build_messages
from app.models.claim import Claim
from app.models.thread import Thread
from app.schemas.instrument import InstrumentDescriptor
from app.services.evidence import RELATION_KINDS
from app.toolbench.registry import InstrumentRegistry
from app.toolbench.registry import registry as _production_registry

# A sane completion budget for the planning call — a plan of a few runs is a few KB. This is the
# request's max OUTPUT tokens; the pass-level token ceiling (agent_pass_max_tokens) is only recorded
# today, not enforced — real budget enforcement lands in 0.12.5 (see agent/llm.py).
PLAN_COMPLETION_MAX_TOKENS = 4096

# The JSON response format hint for providers that honour it (OpenRouter passes it through).
_JSON_RESPONSE_FORMAT = {"type": "json_object"}


class PlannedRun(BaseModel):
    """One instrument run the model proposes.

    ``instrument`` + ``inputs`` are the actionable core (structurally required — a run without them
    is malformed and fails the whole plan parse). ``claim_id`` / ``relation_kind`` are optional
    targeting; ``rationale`` is non-essential metadata (defaulted, so a missing rationale never
    fails the parse). Unknown keys are ignored — a chatty model does not break the plan.
    """

    model_config = ConfigDict(extra="ignore")

    instrument: str
    inputs: dict[str, Any]
    claim_id: UUID | None = None
    relation_kind: str | None = None
    rationale: str = ""


class AgentPlan(BaseModel):
    """The model's proposed plan — a list of runs (empty is valid: "nothing to do")."""

    model_config = ConfigDict(extra="ignore")

    runs: list[PlannedRun] = Field(default_factory=list)


@dataclass(frozen=True)
class PlanResult:
    """The planner's output: the runnable (validated, capped) runs, the dropped records, and usage.

    ``proposed_count`` is the raw number of runs the model proposed
    (``len(runnable) + len(dropped)``) — recorded by the orchestrator as ``AgentRun.planned_count``.
    Each ``dropped`` record follows the ``AgentRun`` step shape with ``status="dropped_invalid"``
    and a ``reason``.
    """

    runnable: list[PlannedRun]
    dropped: list[dict[str, Any]] = field(default_factory=list)
    tokens_used: int = 0
    proposed_count: int = 0


def _parse_plan(text: str) -> AgentPlan:
    """Strip any markdown fence, parse JSON, validate against :class:`AgentPlan`.

    Any failure — non-JSON, wrong shape, a structurally malformed run — is an ``AgentLlmError``.
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # Tolerate a ```json … ``` fence some models emit despite the response-format hint.
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
    try:
        raw = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError) as exc:
        raise AgentLlmError(f"planner returned non-JSON content: {exc}") from exc
    try:
        return AgentPlan.model_validate(raw)
    except ValidationError as exc:
        raise AgentLlmError(f"planner JSON did not match the plan schema: {exc}") from exc


def _dropped(index: int, run: PlannedRun, reason: str, detail: str | None = None) -> dict[str, Any]:
    """A recorded dropped-step, following the ``AgentRun`` step JSON shape."""
    return {
        "index": index,
        "instrument": run.instrument,
        "inputs": run.inputs,
        "claim_id": str(run.claim_id) if run.claim_id is not None else None,
        "relation_kind": run.relation_kind,
        "rationale": run.rationale,
        "status": "dropped_invalid",
        "reason": reason,
        "detail": detail,
    }


async def plan(
    thread: Thread,
    open_claims: list[Claim],
    catalog: list[InstrumentDescriptor],
    model: str,
    *,
    llm: LlmClient,
    max_runs: int,
    registry: InstrumentRegistry | None = None,
    timeout: float | None = None,
) -> PlanResult:
    """Plan a bounded sequence of instrument runs for ``thread``. The single LLM call of a pass.

    ``catalog`` feeds the prompt (the tool menu); ``registry`` (defaults to the production one)
    resolves each proposed instrument for validation — pass a matching pair in tests. ``max_runs``
    is the per-pass safety cap the runnable list is truncated to.
    """
    reg = registry if registry is not None else _production_registry
    open_claim_ids = {claim.id for claim in open_claims}

    response = await llm.complete(
        model=model,
        messages=build_messages(thread, open_claims, catalog),
        response_format=_JSON_RESPONSE_FORMAT,
        timeout=timeout,
        max_tokens=PLAN_COMPLETION_MAX_TOKENS,
    )
    try:
        parsed = _parse_plan(response.text)
    except AgentLlmError as exc:
        # The call completed (and cost tokens) but the body was unusable — attach the spend so the
        # orchestrator records it on the failed trace instead of losing it.
        exc.tokens_used = response.tokens_used
        raise

    runnable: list[PlannedRun] = []
    dropped: list[dict[str, Any]] = []

    for index, run in enumerate(parsed.runs):
        instrument = reg.get(run.instrument)
        if instrument is None:
            dropped.append(_dropped(index, run, "unknown_instrument"))
            continue
        # Structural anti-injection: a claim target must be one the model was actually offered.
        if run.claim_id is not None and run.claim_id not in open_claim_ids:
            dropped.append(_dropped(index, run, "unknown_claim"))
            continue
        if run.relation_kind is not None:
            if run.claim_id is None:
                dropped.append(_dropped(index, run, "relation_kind_without_claim"))
                continue
            if run.relation_kind not in RELATION_KINDS:
                dropped.append(_dropped(index, run, "invalid_relation_kind"))
                continue
        try:
            instrument.InputModel.model_validate(run.inputs)
        except ValidationError as exc:
            dropped.append(_dropped(index, run, "invalid_inputs", detail=str(exc)))
            continue
        runnable.append(run)

    # Truncate to the per-pass safety cap; record the overflow as dropped so the trace is honest.
    if len(runnable) > max_runs:
        for offset, run in enumerate(runnable[max_runs:]):
            dropped.append(_dropped(max_runs + offset, run, "max_runs"))
        runnable = runnable[:max_runs]

    return PlanResult(
        runnable=runnable,
        dropped=dropped,
        tokens_used=response.tokens_used,
        proposed_count=len(parsed.runs),
    )
