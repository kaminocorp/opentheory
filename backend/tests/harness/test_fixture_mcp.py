"""Fixture MCP inventory and stubs — in-process and stdio, no ledger."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.harness.composition import TOOL_STEMS
from app.harness.fixture_mcp import (
    STUB_DETAIL,
    assert_inventory,
    call_tool,
    list_tools,
    tool_stems,
)

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def test_fixture_inventory_matches_composition() -> None:
    assert_inventory()
    assert tool_stems() == TOOL_STEMS
    assert {tool["name"] for tool in list_tools()} == set(TOOL_STEMS)


def test_echo_nonce_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENTHEORY_PROBE_NONCE", "n-42")
    assert call_tool("echo_nonce") == {
        "echo": "n-42",
        "env_nonce": "n-42",
        "stub": True,
    }
    assert call_tool("echo_nonce", {"nonce": "override"})["echo"] == "override"


def test_run_instrument_is_stub() -> None:
    result = call_tool("run_instrument", {"name": "z3.prove", "input": {}})
    assert result["stub"] is True
    assert result["minted"] is False
    assert result["status"] == "undecided"
    assert result["detail"] == STUB_DETAIL
    assert result["instrument"] == "z3.prove"


def test_create_checkpoint_is_stub() -> None:
    result = call_tool("create_checkpoint", {"summary": "should not land"})
    assert result["stub"] is True
    assert result["minted"] is False
    assert result["checkpoint_id"] is None
    assert result["detail"] == STUB_DETAIL


def test_read_helpers_are_empty_stubs() -> None:
    assert call_tool("list_claims", {"project_id": "p"})["claims"] == []
    assert call_tool("get_thread_context", {"thread_id": "t"})["open_claims"] == []
    assert call_tool("get_budget", {"project_id": "p"})["available"] is None


def test_unknown_tool_raises() -> None:
    with pytest.raises(KeyError, match="unknown fixture tool"):
        call_tool("query")


def test_stdio_lists_exact_tools() -> None:
    env = {**os.environ, "PYTHONPATH": str(BACKEND_ROOT)}
    proc = subprocess.Popen(
        [sys.executable, "-m", "app.harness.fixture_mcp"],
        cwd=BACKEND_ROOT,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert proc.stdin is not None
    assert proc.stdout is not None
    _write_rpc(
        proc,
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    )
    _write_rpc(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    proc.stdin.close()
    init = _read_rpc(proc)
    listed = _read_rpc(proc)
    proc.wait(timeout=5)
    assert init["result"]["serverInfo"]["name"] == "opentheory"
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
