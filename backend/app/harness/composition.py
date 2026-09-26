"""Fail closed on changes to the pinned runtime's composed capability tree.

Milestone 0 (`0.40.0`) verifies the authored Cordis patch and the exact MCP
inventory. It does not boot the DeepSeek Harness SDK, does not call
OpenRouter, and does not write the ledger. The SDK pin lives here so a
later extra (`[harness]`) cannot silently drift from what we documented.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

PATCH = Path(__file__).with_name("opentheory.cordis.yml")
VERSION = "0.1.5rc1"
MCP_SERVER_NAME = "opentheory"
MCP_CLIENT_PACKAGE = "@deepseek-ai/dsh-mcp-client"
LLM_PROVIDER_PACKAGE = "@deepseek-ai/dsh-llm-pi-ai"

# Stems the fixture and the live OT plugin may expose. The harness
# prefixes MCP tools as mcp__<serverName>__<stem>.
DOMAIN_TOOL_STEMS = frozenset(
    {
        "run_instrument",
        "create_checkpoint",
        "list_claims",
        "get_thread_context",
        "get_budget",
    }
)
PROBE_TOOL_STEMS = frozenset({"echo_nonce"})
TOOL_STEMS = DOMAIN_TOOL_STEMS | PROBE_TOOL_STEMS
TOOL_NAMES = frozenset(f"mcp__{MCP_SERVER_NAME}__{name}" for name in TOOL_STEMS)

# Pinned sdk-minimal active set (OpenWorld prior art, OT names). The patch
# does not re-list these; it disables the coding tools and inserts OT extras.
ACTIVE = {
    "sdk-app-startup": "@deepseek-ai/dsh-sdk-app",
    "sdk-jsonrpc-server": "@deepseek-ai/dsh-sdk-jsonrpc-server",
    "session-projection": "@deepseek-ai/dsh-session-projection",
    "timer": "@deepseek-ai/cordis-plugin-timer",
    "llm": "@deepseek-ai/dsh-llm",
    "session": "@deepseek-ai/dsh-session",
    "session-title": "@deepseek-ai/dsh-session-title",
    "system-prompt": "@deepseek-ai/dsh-system-prompt",
    "tools": "@deepseek-ai/dsh-tools",
    "agent": "@deepseek-ai/dsh-agent",
    "llm-retry": "@deepseek-ai/dsh-llm-retry",
    "jobs": "@deepseek-ai/dsh-jobs-local",
    "invariants": "@deepseek-ai/dsh-invariants",
    "session-invariant": "@deepseek-ai/dsh-session/invariant",
    "agent-invariant": "@deepseek-ai/dsh-agent/invariant",
    "scope-invariant": "@deepseek-ai/dsh-scope/invariant",
    "agent-loop-invariant": "@deepseek-ai/dsh-agent-loop/invariant",
    "agent-loop": "@deepseek-ai/dsh-agent-loop",
    "sessions": "@deepseek-ai/dsh-session-persistence-jsonl",
    "llm-pi-ai": "@deepseek-ai/dsh-llm-pi-ai",
    "opentheory-mcp": "@deepseek-ai/dsh-mcp-client",
}
DISABLED = frozenset(
    {
        "deepseek-llm-api-extensions",
        "session-log-deepseek",
        "plugin-package-inventory-deepseek",
        "llm-deepseek",
        "sandbox",
        "sandbox-policy",
        "subprocess",
        "pty",
        "terminal-bash",
        "terminal-pwsh",
        "persistent-bash",
        "persistent-pwsh",
    }
)
INSERT_IDS = ("llm-pi-ai", "opentheory-mcp")
SYSTEM_PROMPT_ID = "system-prompt"

_FORBIDDEN_PERSONA = (
    "hospitality",
    "venue",
    "describe_schema",
    "render_figure",
    "sql assistant",
)
_REQUIRED_PERSONA = ("research contributor", "run_instrument", "create_checkpoint")


class CompositionError(ValueError):
    """The authored Cordis patch drifted from the fail-closed inventory."""


@dataclass(frozen=True)
class PatchEntry:
    id: str
    disabled: bool = False
    name: str | None = None
    config: dict[str, Any] | None = None


@dataclass(frozen=True)
class CordisPatch:
    disabled: tuple[PatchEntry, ...]
    system_prompt: PatchEntry
    inserts: tuple[PatchEntry, ...]


def load_patch(path: Path | None = None) -> CordisPatch:
    """Parse the authored Cordis patch. Raises ``CompositionError`` on drift."""
    source = (path or PATCH).read_text(encoding="utf-8")
    return parse_patch(source)


def parse_patch(source: str) -> CordisPatch:
    items = _parse_top_level_items(source)
    disabled: list[PatchEntry] = []
    inserts: list[PatchEntry] = []
    system_prompt: PatchEntry | None = None

    for item in items:
        if "insert" in item:
            extra = set(item) - {"insert"}
            if extra:
                raise CompositionError(f"insert item has unexpected keys: {sorted(extra)}")
            raw_inserts = item["insert"]
            if not isinstance(raw_inserts, list) or not raw_inserts:
                raise CompositionError("insert must be a non-empty list")
            for raw in raw_inserts:
                inserts.append(_entry_from_mapping(raw, allow_disabled=False))
            continue

        entry = _entry_from_mapping(item, allow_disabled=True)
        if entry.id == SYSTEM_PROMPT_ID:
            if entry.disabled:
                raise CompositionError("system-prompt must stay active with an OT persona")
            system_prompt = entry
            continue
        if not entry.disabled:
            raise CompositionError(f"top-level id {entry.id!r} must be disabled: true")
        disabled.append(entry)

    if system_prompt is None:
        raise CompositionError("system-prompt override is missing")
    return CordisPatch(
        disabled=tuple(disabled),
        system_prompt=system_prompt,
        inserts=tuple(inserts),
    )


def verify(*, patch: CordisPatch | None = None, version: str = VERSION) -> None:
    """Assert the on-disk (or supplied) patch matches the pinned inventory."""
    if version != VERSION:
        raise CompositionError(f"runtime pin must be {VERSION}, got {version!r}")
    loaded = patch if patch is not None else load_patch()
    _verify_disabled(loaded)
    _verify_inserts(loaded)
    _verify_persona(loaded)
    _verify_mcp(loaded)


def _verify_disabled(patch: CordisPatch) -> None:
    got = {entry.id for entry in patch.disabled}
    if got != set(DISABLED):
        raise CompositionError(
            "disabled plugin inventory drifted: "
            f"missing={sorted(set(DISABLED) - got)} extra={sorted(got - set(DISABLED))}"
        )
    if any(not entry.disabled for entry in patch.disabled):
        raise CompositionError("every stripped plugin must be disabled: true")


def _verify_inserts(patch: CordisPatch) -> None:
    got = tuple(entry.id for entry in patch.inserts)
    if got != INSERT_IDS:
        raise CompositionError(f"insert inventory must be {INSERT_IDS}, got {got}")
    names = {entry.id: entry.name for entry in patch.inserts}
    if names["llm-pi-ai"] != LLM_PROVIDER_PACKAGE:
        raise CompositionError(f"llm-pi-ai must be {LLM_PROVIDER_PACKAGE}")
    if names["opentheory-mcp"] != MCP_CLIENT_PACKAGE:
        raise CompositionError(f"opentheory-mcp must be {MCP_CLIENT_PACKAGE}")


def _verify_persona(patch: CordisPatch) -> None:
    config = patch.system_prompt.config or {}
    persona = " ".join(str(config.get("personaPrefix") or "").split()).lower()
    if not persona:
        raise CompositionError("system-prompt personaPrefix is required")
    for needle in _FORBIDDEN_PERSONA:
        if needle in persona:
            raise CompositionError(f"persona must not carry {needle!r} (hospitality prior art)")
    missing = [needle for needle in _REQUIRED_PERSONA if needle not in persona]
    if missing:
        raise CompositionError(f"persona is missing required research voice: {missing}")
    if config.get("includeHarnessIdentity") is not False:
        raise CompositionError("includeHarnessIdentity must be false")
    if config.get("includeRuntimeContext") is not False:
        raise CompositionError("includeRuntimeContext must be false")


def _verify_mcp(patch: CordisPatch) -> None:
    mcp = next(entry for entry in patch.inserts if entry.id == "opentheory-mcp")
    config = mcp.config or {}
    if config.get("serverName") != MCP_SERVER_NAME:
        raise CompositionError(f"MCP serverName must be {MCP_SERVER_NAME!r}")
    if config.get("transport") != "stdio":
        raise CompositionError("MCP transport must be stdio")
    if config.get("failOnStartupError") is not True:
        raise CompositionError("MCP failOnStartupError must be true")
    reconnect = config.get("reconnect") or {}
    if reconnect.get("enabled") is not False:
        raise CompositionError("MCP reconnect must be disabled")


def _entry_from_mapping(raw: Any, *, allow_disabled: bool) -> PatchEntry:
    if not isinstance(raw, dict) or "id" not in raw:
        raise CompositionError(f"plugin entry must be a mapping with id, got {raw!r}")
    unknown = set(raw) - {"id", "disabled", "name", "config"}
    if unknown:
        raise CompositionError(f"plugin {raw.get('id')!r} has unexpected keys: {sorted(unknown)}")
    disabled = bool(raw.get("disabled", False))
    if disabled and not allow_disabled:
        raise CompositionError(f"inserted plugin {raw['id']!r} must not be disabled")
    config = raw.get("config")
    if config is not None and not isinstance(config, dict):
        raise CompositionError(f"plugin {raw['id']!r} config must be a mapping")
    name = raw.get("name")
    if name is not None and not isinstance(name, str):
        raise CompositionError(f"plugin {raw['id']!r} name must be a string")
    return PatchEntry(id=str(raw["id"]), disabled=disabled, name=name, config=config)


def _parse_top_level_items(source: str) -> list[dict[str, Any]]:
    """Parse the small Cordis-patch YAML subset we author. No PyYAML required."""
    lines = source.splitlines()
    items: list[dict[str, Any]] = []
    i = 0
    while i < len(lines):
        raw = lines[i]
        stripped = raw.split("#", 1)[0].rstrip()
        if not stripped:
            i += 1
            continue
        if not stripped.startswith("- "):
            raise CompositionError(f"unexpected top-level line: {raw!r}")
        if raw.startswith(" ") or raw.startswith("\t"):
            raise CompositionError(f"top-level item must start at column 0: {raw!r}")
        item, i = _parse_list_item(lines, i, indent=0)
        items.append(item)
    if not items:
        raise CompositionError("cordis patch is empty")
    return items


def _parse_list_item(lines: list[str], index: int, *, indent: int) -> tuple[Any, int]:
    raw = lines[index]
    body = raw[indent + 2 :]
    stripped_body = body.split("#", 1)[0].rstrip()
    if stripped_body and ":" not in stripped_body:
        return _parse_scalar(stripped_body.strip()), index + 1
    mapping: dict[str, Any] = {}
    if stripped_body:
        key, value, consumed = _parse_key_value(lines, index, indent + 2, stripped_body)
        mapping[key] = value
        index = consumed
    else:
        index += 1
    index = _parse_mapping_body(lines, index, indent=indent + 2, into=mapping)
    return mapping, index


def _parse_mapping_body(
    lines: list[str], index: int, *, indent: int, into: dict[str, Any]
) -> int:
    while index < len(lines):
        raw = lines[index]
        stripped = raw.split("#", 1)[0].rstrip()
        if not stripped:
            index += 1
            continue
        current = _leading_spaces(raw)
        if current < indent:
            return index
        if current > indent:
            raise CompositionError(f"unexpected indent on {raw!r}")
        if stripped.lstrip().startswith("- "):
            return index
        key, value, index = _parse_key_value(lines, index, indent, stripped)
        into[key] = value
    return index


def _parse_key_value(
    lines: list[str], index: int, indent: int, body: str
) -> tuple[str, Any, int]:
    if ":" not in body:
        raise CompositionError(f"expected key: value, got {body!r}")
    key, rest = body.split(":", 1)
    key = key.strip()
    rest = rest.strip()
    if not key:
        raise CompositionError(f"empty key on {lines[index]!r}")
    if rest == ">-" or rest == "|-" or rest == ">" or rest == "|":
        text, nxt = _parse_folded_block(lines, index + 1, indent=indent + 2)
        return key, text, nxt
    if rest == "":
        nxt = index + 1
        # Skip blank / comment lines to see what follows.
        peek = nxt
        while peek < len(lines):
            candidate = lines[peek].split("#", 1)[0].rstrip()
            if candidate:
                break
            peek += 1
        else:
            return key, {}, nxt
        peek_indent = _leading_spaces(lines[peek])
        if peek_indent <= indent:
            return key, {}, nxt
        peek_body = candidate.lstrip()
        if peek_body.startswith("- "):
            values, nxt = _parse_nested_list(lines, peek, indent=peek_indent)
            return key, values, nxt
        nested: dict[str, Any] = {}
        nxt = _parse_mapping_body(lines, peek, indent=peek_indent, into=nested)
        return key, nested, nxt
    return key, _parse_scalar(rest), index + 1


def _parse_nested_list(
    lines: list[str], index: int, *, indent: int
) -> tuple[list[Any], int]:
    items: list[Any] = []
    while index < len(lines):
        raw = lines[index]
        stripped = raw.split("#", 1)[0].rstrip()
        if not stripped:
            index += 1
            continue
        current = _leading_spaces(raw)
        if current < indent:
            return items, index
        if current != indent or not stripped.lstrip().startswith("- "):
            return items, index
        item, index = _parse_list_item(lines, index, indent=indent)
        items.append(item)
    return items, index


def _parse_folded_block(lines: list[str], index: int, *, indent: int) -> tuple[str, int]:
    chunks: list[str] = []
    while index < len(lines):
        raw = lines[index]
        if not raw.strip():
            if chunks:
                chunks.append("")
            index += 1
            continue
        if _leading_spaces(raw) < indent:
            break
        chunks.append(raw[indent:] if len(raw) >= indent else raw.strip())
        index += 1
    return " ".join(part.strip() for part in chunks if part.strip()), index


def _parse_scalar(value: str) -> Any:
    if value.startswith("!!js "):
        return value[5:]
    if value.startswith("'") and value.endswith("'") and len(value) >= 2:
        return value[1:-1]
    if value.startswith('"') and value.endswith('"') and len(value) >= 2:
        return value[1:-1]
    if value == "true":
        return True
    if value == "false":
        return False
    if value == "null":
        return None
    try:
        return int(value)
    except ValueError:
        return value


def _leading_spaces(line: str) -> int:
    return len(line) - len(line.lstrip(" "))
