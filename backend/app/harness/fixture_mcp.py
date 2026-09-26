"""Milestone-0 fixture MCP — probe tools that never touch the ledger.

The live OpenTheory plugin (later) will expose the same stems against JWT
Actor + membership + ``run_instrument`` / ``create_checkpoint``. This module
is the fail-closed stand-in so composition and a stdio round-trip can be
tested without ``OPENROUTER_API_KEY``, the DeepSeek SDK, or Postgres.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from typing import Any

from app.harness.composition import DOMAIN_TOOL_STEMS, PROBE_TOOL_STEMS, TOOL_STEMS

SERVER_NAME = "opentheory"
PROTOCOL_VERSION = "2024-11-05"

STUB_DETAIL = "m0_fixture_does_not_touch_the_ledger"

ToolHandler = Callable[[dict[str, Any]], dict[str, Any]]


def _echo_nonce(arguments: dict[str, Any]) -> dict[str, Any]:
    env_nonce = os.environ.get("OPENTHEORY_PROBE_NONCE", "")
    requested = arguments.get("nonce")
    return {
        "echo": env_nonce if requested is None else requested,
        "env_nonce": env_nonce,
        "stub": True,
    }


def _run_instrument(arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "stub": True,
        "tool": "run_instrument",
        "instrument": arguments.get("name"),
        "status": "undecided",
        "detail": STUB_DETAIL,
        "minted": False,
    }


def _create_checkpoint(arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "stub": True,
        "tool": "create_checkpoint",
        "summary": arguments.get("summary"),
        "detail": STUB_DETAIL,
        "minted": False,
        "checkpoint_id": None,
    }


def _list_claims(arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "stub": True,
        "tool": "list_claims",
        "project_id": arguments.get("project_id"),
        "claims": [],
        "detail": STUB_DETAIL,
    }


def _get_thread_context(arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "stub": True,
        "tool": "get_thread_context",
        "thread_id": arguments.get("thread_id"),
        "open_claims": [],
        "detail": STUB_DETAIL,
    }


def _get_budget(arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "stub": True,
        "tool": "get_budget",
        "project_id": arguments.get("project_id"),
        "available": None,
        "detail": STUB_DETAIL,
    }


_HANDLERS: dict[str, ToolHandler] = {
    "echo_nonce": _echo_nonce,
    "run_instrument": _run_instrument,
    "create_checkpoint": _create_checkpoint,
    "list_claims": _list_claims,
    "get_thread_context": _get_thread_context,
    "get_budget": _get_budget,
}

_TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "echo_nonce": {
        "description": "M0 probe: echo a nonce. Never writes the ledger.",
        "inputSchema": {
            "type": "object",
            "properties": {"nonce": {"type": "string"}},
        },
    },
    "run_instrument": {
        "description": (
            "M0 stub of run_instrument. Returns a fixed undecided payload "
            "and mints nothing. Live binding is a later slice."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "input": {"type": "object"},
            },
        },
    },
    "create_checkpoint": {
        "description": (
            "M0 stub of create_checkpoint. Returns minted=false. "
            "Live binding is a later slice."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"summary": {"type": "string"}},
        },
    },
    "list_claims": {
        "description": "M0 stub of a claims read. Returns an empty list.",
        "inputSchema": {
            "type": "object",
            "properties": {"project_id": {"type": "string"}},
        },
    },
    "get_thread_context": {
        "description": "M0 stub of thread + open-claim context.",
        "inputSchema": {
            "type": "object",
            "properties": {"thread_id": {"type": "string"}},
        },
    },
    "get_budget": {
        "description": "M0 stub of project ComputeDebit available.",
        "inputSchema": {
            "type": "object",
            "properties": {"project_id": {"type": "string"}},
        },
    },
}


def tool_stems() -> frozenset[str]:
    """Exact fixture inventory — must match ``composition.TOOL_STEMS``."""
    return frozenset(_HANDLERS)


def list_tools() -> list[dict[str, Any]]:
    return [
        {"name": name, **_TOOL_SCHEMAS[name]}
        for name in sorted(_HANDLERS)
    ]


def call_tool(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    if name not in _HANDLERS:
        raise KeyError(f"unknown fixture tool: {name}")
    return _HANDLERS[name](arguments or {})


def assert_inventory() -> None:
    """Fail closed if the fixture drifts from the composed tool stems."""
    got = tool_stems()
    if got != TOOL_STEMS:
        raise RuntimeError(
            "fixture MCP inventory drifted: "
            f"missing={sorted(TOOL_STEMS - got)} extra={sorted(got - TOOL_STEMS)}"
        )
    if DOMAIN_TOOL_STEMS & PROBE_TOOL_STEMS:
        raise RuntimeError("probe stems must stay disjoint from domain stems")


def _read_message() -> dict[str, Any] | None:
    headers: dict[str, str] = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line in {b"\r\n", b"\n"}:
            break
        decoded = line.decode("utf-8")
        if ":" not in decoded:
            continue
        key, value = decoded.split(":", 1)
        headers[key.strip().lower()] = value.strip()
    length = int(headers.get("content-length", "0"))
    if length <= 0:
        return None
    payload = sys.stdin.buffer.read(length)
    if not payload:
        return None
    return json.loads(payload.decode("utf-8"))


def _write_message(message: dict[str, Any]) -> None:
    payload = json.dumps(message, separators=(",", ":")).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(payload)}\r\n\r\n".encode())
    sys.stdout.buffer.write(payload)
    sys.stdout.buffer.flush()
    _maybe_log(message)


def _maybe_log(message: dict[str, Any]) -> None:
    path = os.environ.get("OPENTHEORY_PROBE_LOG")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(message) + "\n")


def _handle(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    msg_id = message.get("id")
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": "0.40.0"},
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
            result = call_tool(str(name), params.get("arguments") or {})
        except KeyError as exc:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": str(exc)},
            }
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "content": [{"type": "text", "text": json.dumps(result)}],
                "isError": False,
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


def serve_stdio() -> None:
    """JSON-RPC MCP over stdin/stdout. No SDK, no ledger, no network."""
    assert_inventory()
    while True:
        message = _read_message()
        if message is None:
            return
        reply = _handle(message)
        if reply is not None:
            _write_message(reply)


def main() -> None:
    serve_stdio()


if __name__ == "__main__":
    main()
