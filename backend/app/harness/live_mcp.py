"""Live OpenTheory MCP — JWT Actor + membership + existing chokepoints.

Same stems as the M0 fixture. This module is the domain door: it authenticates,
authorizes membership, and calls ``run_instrument`` / ``create_checkpoint``.
It does not mint a ``Checkpoint`` itself. FastAPI does not import this package.
``AGENT_LOOP_ENABLED`` is untouched.

Stdio JSON-RPC. Credentials come from ``app.harness.auth`` (JWT file preferred).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Mapping
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.session import AsyncSessionLocal
from app.harness.auth import resolve_mcp_actor
from app.harness.composition import DOMAIN_TOOL_STEMS, PROBE_TOOL_STEMS, TOOL_STEMS
from app.harness.protocol import (
    PROTOCOL_VERSION,
    SERVER_NAME,
    read_message,
    write_message,
)
from app.models.actor import Actor
from app.models.enums import ThreadStage
from app.schemas.checkpoint import CheckpointCreate, CheckpointRefInput
from app.schemas.claim import SETTLED_HEADLINES, ClaimGrounding
from app.services import checkpoints as checkpoint_service
from app.services import claims as claim_service
from app.services import compute as compute_service
from app.services import funding as funding_service
from app.services import grounding as grounding_service
from app.services import threads as thread_service
from app.services import validations as validation_service
from app.services.project_members import ensure_is_member, ensure_member_of_thread
from app.services.tool_runs import run_instrument as run_instrument_service
from app.toolbench import registry
from app.toolbench.grading import raise_path

VERSION = "0.41.0"

ToolHandler = Callable[[AsyncSession, Actor, dict[str, Any]], Awaitable[dict[str, Any]]]


def _echo_nonce(arguments: dict[str, Any]) -> dict[str, Any]:
    import os

    env_nonce = os.environ.get("OPENTHEORY_PROBE_NONCE", "")
    requested = arguments.get("nonce")
    return {
        "echo": env_nonce if requested is None else requested,
        "env_nonce": env_nonce,
        "stub": False,
        "live": True,
    }


def _uuid(value: Any, field: str) -> UUID:
    if value is None or value == "":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"{field} is required")
    try:
        return UUID(str(value))
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"{field} must be a UUID"
        ) from exc


def _optional_uuid(value: Any, field: str) -> UUID | None:
    if value is None or value == "":
        return None
    return _uuid(value, field)


async def _refuse_if_exhausted(db: AsyncSession, project_id: UUID) -> None:
    """Refuse a write when a funded project has no remaining ComputeDebit pot.

    Unfunded projects (``funded == 0``) are not exhausted — humans can still run
    instruments there, and this door does not invent a parallel debit. A later
    gateway (``0.42.0``) bills tokens through ``record_compute_debit``.
    """
    budget = await funding_service.project_budget(db, project_id)
    if budget.funded > 0 and budget.available <= 0:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            compute_service.BUDGET_EXHAUSTED,
        )


async def _run_instrument(
    db: AsyncSession, actor: Actor, arguments: dict[str, Any]
) -> dict[str, Any]:
    project_id = _uuid(arguments.get("project_id"), "project_id")
    name = arguments.get("name")
    if not name or not isinstance(name, str):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "name is required")
    instrument = registry.get(name)
    if instrument is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown instrument {name!r}")
    await ensure_is_member(db, project_id, actor)
    await _refuse_if_exhausted(db, project_id)
    raw_input = arguments.get("inputs")
    if raw_input is None:
        raw_input = arguments.get("input")
    if raw_input is None:
        raw_input = {}
    if not isinstance(raw_input, dict):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "input must be an object")
    assumptions = arguments.get("assumptions") or {}
    if not isinstance(assumptions, dict):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "assumptions must be an object"
        )
    result = await run_instrument_service(
        db,
        project_id,
        instrument,
        actor,
        inputs=raw_input,
        assumptions=assumptions,
        thread_id=_optional_uuid(arguments.get("thread_id"), "thread_id"),
        branch_id=_optional_uuid(arguments.get("branch_id"), "branch_id"),
        claim_id=_optional_uuid(arguments.get("claim_id"), "claim_id"),
        relation_kind=arguments.get("relation_kind"),
    )
    return {
        "ok": True,
        "stub": False,
        "tool": "run_instrument",
        "instrument": instrument.name,
        "status": result.status.value,
        "minted": True,
        "checkpoint_id": str(result.checkpoint.id),
        "artifact_id": str(result.artifact_id),
        "evidence_id": str(result.evidence_id) if result.evidence_id else None,
        "content_hash": result.content_hash,
    }


def _refs_from_arguments(raw: Any) -> list[CheckpointRefInput]:
    if not raw:
        return []
    if not isinstance(raw, list):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "refs must be a list")
    refs: list[CheckpointRefInput] = []
    for item in raw:
        if not isinstance(item, dict):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "each ref must be an object"
            )
        refs.append(
            CheckpointRefInput(
                target_type=str(item.get("target_type") or ""),
                target_id=_uuid(item.get("target_id"), "refs.target_id"),
                role=str(item.get("role") or ""),
            )
        )
    return refs


async def _create_checkpoint(
    db: AsyncSession, actor: Actor, arguments: dict[str, Any]
) -> dict[str, Any]:
    project_id = _uuid(arguments.get("project_id"), "project_id")
    summary = arguments.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "summary is required")
    await ensure_is_member(db, project_id, actor)
    await _refuse_if_exhausted(db, project_id)
    content = arguments.get("content") or {}
    if not isinstance(content, dict):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "content must be an object")
    stage_raw = arguments.get("stage")
    stage: ThreadStage | None = None
    if stage_raw:
        try:
            stage = ThreadStage(stage_raw)
        except ValueError as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, f"invalid stage: {stage_raw!r}"
            ) from exc
    parent_ids = arguments.get("parent_ids") or []
    if not isinstance(parent_ids, list):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "parent_ids must be a list"
        )
    checkpoint = await checkpoint_service.create_checkpoint(
        db,
        project_id,
        CheckpointCreate(
            thread_id=_optional_uuid(arguments.get("thread_id"), "thread_id"),
            branch_id=_optional_uuid(arguments.get("branch_id"), "branch_id"),
            summary=summary.strip(),
            stage=stage,
            content=content,
            notes=arguments.get("notes"),
            parent_ids=[_uuid(item, "parent_ids") for item in parent_ids],
            refs=_refs_from_arguments(arguments.get("refs")),
        ),
        actor,
    )
    return {
        "ok": True,
        "stub": False,
        "tool": "create_checkpoint",
        "summary": checkpoint.summary,
        "minted": True,
        "checkpoint_id": str(checkpoint.id),
        "contribution_kind": checkpoint.contribution_kind,
    }


async def _list_claims(
    db: AsyncSession, actor: Actor, arguments: dict[str, Any]
) -> dict[str, Any]:
    project_id = _uuid(arguments.get("project_id"), "project_id")
    await ensure_is_member(db, project_id, actor)
    thread_id = _optional_uuid(arguments.get("thread_id"), "thread_id")
    if thread_id is not None:
        thread = await ensure_member_of_thread(db, thread_id, actor)
        if thread.project_id != project_id:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Thread belongs to a different project"
            )
        claims = await claim_service.list_claims(db, thread_id)
    else:
        claims = await claim_service.list_project_claims(db, project_id)
    return {
        "ok": True,
        "stub": False,
        "tool": "list_claims",
        "project_id": str(project_id),
        "claims": [claim.model_dump(mode="json") for claim in claims],
    }


async def _get_thread_context(
    db: AsyncSession, actor: Actor, arguments: dict[str, Any]
) -> dict[str, Any]:
    thread_id = _uuid(arguments.get("thread_id"), "thread_id")
    thread = await ensure_member_of_thread(db, thread_id, actor)
    summary = await thread_service.get_thread_summary(db, thread_id)
    open_claims = await claim_service.open_claims_for_planner(db, thread_id)
    claim_ids = [claim.id for claim in open_claims]
    by_signal = await validation_service.validations_by_claim(db, claim_ids)
    grounded = await grounding_service.grounding_by_claim(db, claim_ids)
    rendered: list[dict[str, Any]] = []
    for claim in open_claims:
        grounding = grounded.get(claim.id) or ClaimGrounding()
        signal = claim_service.compute_signal(by_signal.get(claim.id, []))
        path = [] if grounding.headline in SETTLED_HEADLINES else raise_path(grounding.support)
        rendered.append(
            {
                "id": str(claim.id),
                "statement": claim.statement,
                "kind": claim.kind.value,
                "signal": signal,
                "grounding": grounding.model_dump(mode="json"),
                "to_raise": path,
                "settled": grounding.headline in SETTLED_HEADLINES,
            }
        )
    return {
        "ok": True,
        "stub": False,
        "tool": "get_thread_context",
        "thread_id": str(thread.id),
        "project_id": str(thread.project_id),
        "thread": summary.model_dump(mode="json"),
        "open_claims": rendered,
    }


def _decimal(value: Decimal) -> str:
    return format(value, "f")


async def _get_budget(
    db: AsyncSession, actor: Actor, arguments: dict[str, Any]
) -> dict[str, Any]:
    project_id = _uuid(arguments.get("project_id"), "project_id")
    await ensure_is_member(db, project_id, actor)
    budget = await funding_service.project_budget(db, project_id)
    return {
        "ok": True,
        "stub": False,
        "tool": "get_budget",
        "project_id": str(budget.project_id),
        "currency": budget.currency,
        "funded": _decimal(budget.funded),
        "spent": _decimal(budget.spent),
        "reserved": _decimal(budget.reserved),
        "available": _decimal(budget.available),
    }


_HANDLERS: dict[str, ToolHandler] = {
    "run_instrument": _run_instrument,
    "create_checkpoint": _create_checkpoint,
    "list_claims": _list_claims,
    "get_thread_context": _get_thread_context,
    "get_budget": _get_budget,
}

_TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "echo_nonce": {
        "description": "Probe: echo a nonce. Never writes the ledger.",
        "inputSchema": {
            "type": "object",
            "properties": {"nonce": {"type": "string"}},
        },
    },
    "run_instrument": {
        "description": (
            "Run a catalog instrument as the JWT Actor and land the result through "
            "run_instrument → create_checkpoint. Exceptions mint nothing."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["project_id", "name"],
            "properties": {
                "project_id": {"type": "string"},
                "name": {"type": "string"},
                "input": {"type": "object"},
                "inputs": {"type": "object"},
                "assumptions": {"type": "object"},
                "thread_id": {"type": "string"},
                "branch_id": {"type": "string"},
                "claim_id": {"type": "string"},
                "relation_kind": {"type": "string"},
            },
        },
    },
    "create_checkpoint": {
        "description": (
            "Create a research-state checkpoint through services.checkpoints.create_checkpoint. "
            "Not a dump of the model transcript. Membership-gated."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["project_id", "summary"],
            "properties": {
                "project_id": {"type": "string"},
                "summary": {"type": "string"},
                "thread_id": {"type": "string"},
                "branch_id": {"type": "string"},
                "content": {"type": "object"},
                "notes": {"type": "string"},
                "parent_ids": {"type": "array", "items": {"type": "string"}},
                "refs": {"type": "array"},
                "stage": {"type": "string"},
            },
        },
    },
    "list_claims": {
        "description": "Member-scoped project (or thread) claims. Read only.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id"],
            "properties": {
                "project_id": {"type": "string"},
                "thread_id": {"type": "string"},
            },
        },
    },
    "get_thread_context": {
        "description": "Thread + open claims + grounding raise lines. Read only.",
        "inputSchema": {
            "type": "object",
            "required": ["thread_id"],
            "properties": {"thread_id": {"type": "string"}},
        },
    },
    "get_budget": {
        "description": "project_budget.available from ComputeDebit. Read only.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id"],
            "properties": {"project_id": {"type": "string"}},
        },
    },
}


def tool_stems() -> frozenset[str]:
    return frozenset(_HANDLERS) | frozenset({"echo_nonce"})


def list_tools() -> list[dict[str, Any]]:
    names = sorted(tool_stems())
    return [{"name": name, **_TOOL_SCHEMAS[name]} for name in names]


def assert_inventory() -> None:
    got = tool_stems()
    if got != TOOL_STEMS:
        raise RuntimeError(
            "live MCP inventory drifted: "
            f"missing={sorted(TOOL_STEMS - got)} extra={sorted(got - TOOL_STEMS)}"
        )
    if DOMAIN_TOOL_STEMS & PROBE_TOOL_STEMS:
        raise RuntimeError("probe stems must stay disjoint from domain stems")


def _http_error_payload(exc: HTTPException, *, tool: str | None = None) -> dict[str, Any]:
    return {
        "ok": False,
        "stub": False,
        "tool": tool,
        "minted": False,
        "checkpoint_id": None,
        "status_code": exc.status_code,
        "detail": exc.detail,
        "error": _error_name(exc.status_code, exc.detail),
    }


def _error_name(status_code: int, detail: Any) -> str:
    if detail == compute_service.BUDGET_EXHAUSTED:
        return compute_service.BUDGET_EXHAUSTED
    return {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        422: "unprocessable",
        503: "busy",
    }.get(status_code, "error")


async def call_tool(
    name: str,
    arguments: dict[str, Any] | None = None,
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    actor: Actor | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Dispatch one live tool. Unknown stems raise ``KeyError`` (fixture parity)."""
    if name == "echo_nonce":
        return _echo_nonce(arguments or {})
    handler = _HANDLERS.get(name)
    if handler is None:
        raise KeyError(f"unknown live tool: {name}")
    factory = session_factory or AsyncSessionLocal
    async with factory() as db:
        try:
            acting = actor if actor is not None else await resolve_mcp_actor(db, env)
            return await handler(db, acting, arguments or {})
        except HTTPException as exc:
            return _http_error_payload(exc, tool=name)
        except Exception as exc:
            # Fail closed: an unexpected exception is not a result and mints nothing.
            # The session context rolls back any uncommitted work.
            return {
                "ok": False,
                "stub": False,
                "tool": name,
                "minted": False,
                "checkpoint_id": None,
                "status_code": 500,
                "detail": str(exc),
                "error": "error",
            }


async def invoke(
    name: str,
    arguments: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Alias for tests — same as :func:`call_tool`."""
    return await call_tool(name, arguments, **kwargs)


async def _handle(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    msg_id = message.get("id")
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": VERSION},
            },
        }
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": list_tools()}}
    if method == "tools/call":
        params = message.get("params") or {}
        name = params.get("name")
        try:
            result = await call_tool(str(name), params.get("arguments") or {})
        except KeyError as exc:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": str(exc)},
            }
        is_error = bool(isinstance(result, dict) and result.get("ok") is False)
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "content": [{"type": "text", "text": json.dumps(result)}],
                "isError": is_error,
            },
        }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}
    if msg_id is None:
        return None
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {"code": -32601, "message": f"method not found: {method}"},
    }


async def serve_stdio() -> None:
    """JSON-RPC MCP over stdin/stdout. One session per tool call."""
    assert_inventory()
    while True:
        message = read_message()
        if message is None:
            return
        reply = await _handle(message)
        if reply is not None:
            write_message(reply)


def main() -> None:
    asyncio.run(serve_stdio())


if __name__ == "__main__":
    main()
