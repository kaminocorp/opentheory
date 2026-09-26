"""Shared stdio JSON-RPC framing for fixture and live MCP servers."""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from app.harness.auth import redact

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "opentheory"


def read_message() -> dict[str, Any] | None:
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


def write_message(message: dict[str, Any]) -> None:
    payload = json.dumps(message, separators=(",", ":")).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(payload)}\r\n\r\n".encode())
    sys.stdout.buffer.write(payload)
    sys.stdout.buffer.flush()
    maybe_log(message)


def maybe_log(message: dict[str, Any]) -> None:
    """Append a *redacted* JSON-RPC message. Bearer values never reach the file."""
    path = os.environ.get("OPENTHEORY_PROBE_LOG")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(redact(message)) + "\n")
