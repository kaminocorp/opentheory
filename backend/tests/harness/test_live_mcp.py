"""Live MCP inventory and fail-closed dispatch — no ledger required."""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.harness.composition import TOOL_STEMS
from app.harness.live_mcp import (
    VERSION,
    assert_inventory,
    call_tool,
    list_tools,
    tool_stems,
)

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def test_live_inventory_matches_composition() -> None:
    assert_inventory()
    assert tool_stems() == TOOL_STEMS
    assert {tool["name"] for tool in list_tools()} == set(TOOL_STEMS)


def test_fastapi_does_not_import_harness() -> None:
    """Boot path stays dark — live MCP is a stdio child, not an API router."""
    for rel in ("app/main.py", "app/api/router.py"):
        source = (BACKEND_ROOT / rel).read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("app.harness"), rel
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("app.harness"), rel


def test_unknown_tool_raises() -> None:
    with pytest.raises(KeyError, match="unknown live tool"):
        # call_tool is async; run via asyncio below if needed — KeyError is sync.
        import asyncio

        asyncio.run(call_tool("query", {}))


def test_echo_nonce_does_not_touch_ledger(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENTHEORY_PROBE_NONCE", "n-live")
    import asyncio

    result = asyncio.run(call_tool("echo_nonce", {}))
    assert result["echo"] == "n-live"
    assert result["live"] is True
    assert result["stub"] is False


def test_stdio_lists_exact_tools() -> None:
    env = {**os.environ, "PYTHONPATH": str(BACKEND_ROOT)}
    proc = subprocess.Popen(
        [sys.executable, "-m", "app.harness.live_mcp"],
        cwd=BACKEND_ROOT,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert proc.stdin is not None
    assert proc.stdout is not None
    _write_rpc(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    _write_rpc(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    proc.stdin.close()
    init = _read_rpc(proc)
    listed = _read_rpc(proc)
    proc.wait(timeout=10)
    assert init["result"]["serverInfo"]["name"] == "opentheory"
    assert init["result"]["serverInfo"]["version"] == VERSION
    names = {tool["name"] for tool in listed["result"]["tools"]}
    assert names == set(TOOL_STEMS)


def _write_rpc(proc: subprocess.Popen[bytes], message: dict) -> None:
    payload = json.dumps(message).encode("utf-8")
    assert proc.stdin is not None
    proc.stdin.write(f"Content-Length: {len(payload)}\r\n\r\n".encode() + payload)
    proc.stdin.flush()


def _read_rpc(proc: subprocess.Popen[bytes]) -> dict:
    assert proc.stdout is not None
    headers: dict[str, str] = {}
    while True:
        line = proc.stdout.readline()
        if not line:
            raise AssertionError(proc.stderr.read().decode() if proc.stderr else "eof")
        if line in {b"\r\n", b"\n"}:
            break
        decoded = line.decode("utf-8")
        key, value = decoded.split(":", 1)
        headers[key.strip().lower()] = value.strip()
    length = int(headers["content-length"])
    payload = proc.stdout.read(length)
    return json.loads(payload.decode("utf-8"))
