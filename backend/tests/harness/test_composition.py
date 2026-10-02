"""Fail-closed Cordis composition — no SDK, no network, no ledger."""

from __future__ import annotations

from copy import deepcopy

import pytest

from app.harness.composition import (
    CAMPAIGN_CHILD_ARGS,
    CAMPAIGN_MODULE,
    DISABLED,
    GATEWAY_MODULE,
    GATEWAY_PYTHON_ENV,
    INSERT_IDS,
    JWT_ENV,
    JWT_FILE_ENV,
    MCP_SERVER_NAME,
    PROJECT_ID_ENV,
    UNMETERED_PROBE_ENV,
    VERSION,
    CompositionError,
    env_interpolation,
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


def test_on_disk_patch_binds_session_owned_campaign_child() -> None:
    patch = load_patch()
    llm = next(entry for entry in patch.inserts if entry.id == "llm-pi-ai")
    mcp = next(entry for entry in patch.inserts if entry.id == "opentheory-mcp")
    assert llm.config is not None
    assert mcp.config is not None
    assert llm.config["command"] == env_interpolation(GATEWAY_PYTHON_ENV)
    assert tuple(llm.config["args"]) == CAMPAIGN_CHILD_ARGS
    assert llm.config["env"][PROJECT_ID_ENV] == env_interpolation(PROJECT_ID_ENV)
    assert mcp.config["env"][PROJECT_ID_ENV] == env_interpolation(PROJECT_ID_ENV)
    assert mcp.config["env"][JWT_FILE_ENV] == env_interpolation(JWT_FILE_ENV)
    assert JWT_ENV not in mcp.config["env"]
    assert UNMETERED_PROBE_ENV not in (llm.config.get("env") or {})
    assert GATEWAY_MODULE not in llm.config["args"]
    assert CAMPAIGN_MODULE in llm.config["args"]


def test_missing_project_id_binding_is_rejected() -> None:
    source = _patch_source().replace(
        f"          {PROJECT_ID_ENV}: !!js process.env.{PROJECT_ID_ENV}\n",
        "",
        1,
    )
    with pytest.raises(CompositionError, match=PROJECT_ID_ENV):
        verify(patch=parse_patch(source))


def test_literal_project_id_is_rejected() -> None:
    source = _patch_source().replace(
        f"!!js process.env.{PROJECT_ID_ENV}",
        "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        1,
    )
    with pytest.raises(CompositionError, match="never a UUID"):
        verify(patch=parse_patch(source))


def test_bare_unmetered_gateway_child_is_rejected() -> None:
    source = _patch_source().replace(
        f"          - {CAMPAIGN_MODULE}\n",
        f"          - {GATEWAY_MODULE}\n",
    )
    with pytest.raises(CompositionError, match="unmetered proxy"):
        verify(patch=parse_patch(source))


def test_unmetered_probe_flag_is_not_the_campaign_composition() -> None:
    source = _patch_source().replace(
        f"          {PROJECT_ID_ENV}: !!js process.env.{PROJECT_ID_ENV}\n",
        (
            f"          {PROJECT_ID_ENV}: !!js process.env.{PROJECT_ID_ENV}\n"
            f"          {UNMETERED_PROBE_ENV}: !!js process.env.{UNMETERED_PROBE_ENV}\n"
        ),
        1,
    )
    with pytest.raises(CompositionError, match="not the campaign composition"):
        verify(patch=parse_patch(source))


def test_jwt_bearer_in_cordis_env_is_rejected() -> None:
    source = _patch_source().replace(
        f"          {JWT_FILE_ENV}: !!js process.env.{JWT_FILE_ENV}\n",
        (
            f"          {JWT_FILE_ENV}: !!js process.env.{JWT_FILE_ENV}\n"
            f"          {JWT_ENV}: !!js process.env.{JWT_ENV}\n"
        ),
    )
    with pytest.raises(CompositionError, match="must not appear in Cordis env"):
        verify(patch=parse_patch(source))


def test_unexpected_top_level_key_is_rejected() -> None:
    source = _patch_source() + "- id: surprise\n  disabled: true\n"
    with pytest.raises(CompositionError, match="disabled plugin inventory drifted"):
        verify(patch=parse_patch(source))


def _patch_source() -> str:
    from app.harness.composition import PATCH

    return PATCH.read_text(encoding="utf-8")
