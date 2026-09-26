"""Fail-closed Cordis composition — no SDK, no network, no ledger."""

from __future__ import annotations

from copy import deepcopy

import pytest

from app.harness.composition import (
    DISABLED,
    INSERT_IDS,
    MCP_SERVER_NAME,
    VERSION,
    CompositionError,
    load_patch,
    parse_patch,
    verify,
)


def test_on_disk_patch_verifies() -> None:
    verify()
    patch = load_patch()
    assert {entry.id for entry in patch.disabled} == set(DISABLED)
    assert tuple(entry.id for entry in patch.inserts) == INSERT_IDS
    assert patch.system_prompt.config is not None
    assert "research contributor" in patch.system_prompt.config["personaPrefix"].lower()


def test_pin_is_documented_rc() -> None:
    assert VERSION == "0.1.5rc1"


def test_disabled_drift_is_rejected() -> None:
    patch = load_patch()
    mutated = deepcopy(patch)
    object.__setattr__(mutated, "disabled", patch.disabled[:-1])
    with pytest.raises(CompositionError, match="disabled plugin inventory drifted"):
        verify(patch=mutated)


def test_enabling_a_stripped_plugin_is_rejected() -> None:
    source = _patch_source().replace(
        "- id: sandbox\n  disabled: true\n",
        "- id: sandbox\n  disabled: false\n",
    )
    with pytest.raises(CompositionError, match="must be disabled"):
        verify(patch=parse_patch(source))


def test_unknown_insert_is_rejected() -> None:
    extra = (
        "    - id: extra-plugin\n"
        "      name: '@deepseek-ai/dsh-not-a-thing'\n"
        "    - id: opentheory-mcp\n"
    )
    source = _patch_source().replace("    - id: opentheory-mcp\n", extra)
    with pytest.raises(CompositionError, match="insert inventory"):
        verify(patch=parse_patch(source))


def test_hospitality_persona_is_rejected() -> None:
    source = _patch_source().replace(
        "You are a research contributor on OpenTheory.",
        "You are a hospitality SQL assistant at a venue.",
    )
    with pytest.raises(CompositionError, match="hospitality"):
        verify(patch=parse_patch(source))


def test_missing_research_voice_is_rejected() -> None:
    source = _patch_source().replace(
        "You are a research contributor on OpenTheory. You act as an Actor",
        "You are an assistant. You act as an Actor",
    )
    with pytest.raises(CompositionError, match="required research voice"):
        verify(patch=parse_patch(source))


def test_version_drift_is_rejected() -> None:
    with pytest.raises(CompositionError, match="runtime pin"):
        verify(version="0.0.0")


def test_mcp_server_name_is_opentheory() -> None:
    patch = load_patch()
    mcp = next(entry for entry in patch.inserts if entry.id == "opentheory-mcp")
    assert mcp.config is not None
    assert mcp.config["serverName"] == MCP_SERVER_NAME


def test_unexpected_top_level_key_is_rejected() -> None:
    source = _patch_source() + "- id: surprise\n  disabled: true\n"
    with pytest.raises(CompositionError, match="disabled plugin inventory drifted"):
        verify(patch=parse_patch(source))


def _patch_source() -> str:
    from app.harness.composition import PATCH

    return PATCH.read_text(encoding="utf-8")
