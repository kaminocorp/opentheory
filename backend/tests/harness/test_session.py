"""Session owner + fail-closed campaign composition (0.44.0) — no live key, no dsh."""

from __future__ import annotations

import ast
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.harness.campaign import (
    INSTRUMENT_ONLY,
    MAY_FUND,
    MAY_MERGE,
    MAY_VALIDATE,
    QUESTION,
    SLUG,
    create_metered_gateway_app,
    open_session,
    reference_spec,
    require_bound_session,
)
from app.harness.composition import UNMETERED_PROBE_ENV
from app.harness.gateway import (
    ALLOWED_EXTRA_BODY_KEYS,
    DEFAULT_MODEL,
    GATEWAY_TOKEN_ENV,
    REFUSED_EXTRA_BODY_KEYS,
    VERSION,
    GatewayClient,
    assert_process_may_serve,
    build_fail_closed_body,
    create_gateway_app,
    unmetered_probe_enabled,
)
from app.harness.session import (
    DEFAULT_MAX_TURNS,
    PROJECT_ID_ENV,
    REASON_TURN_BUDGET,
    SESSION_NOTES,
    HarnessSession,
    session_from_env,
)

BACKEND_ROOT = Path(__file__).resolve().parents[2]
HARNESS_ROOT = BACKEND_ROOT / "app" / "harness"

_OK_BODY = {
    "choices": [{"message": {"content": "pong"}}],
    "usage": {"total_tokens": 5, "prompt_tokens": 3, "completion_tokens": 2},
}


def _gateway(handler) -> GatewayClient:
    return GatewayClient(
        api_key="sk-test",
        base_url="https://openrouter.ai/api/v1",
        transport=httpx.MockTransport(handler),
    )


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
            for alias in node.names:
                modules.add(f"{node.module}.{alias.name}")
    return modules


def test_reference_campaign_is_odd_perfect_and_instrument_only() -> None:
    spec = reference_spec()
    assert spec["slug"] == SLUG == "odd-perfect-numbers"
    assert "odd perfect" in QUESTION.lower()
    assert spec["instrument_only"] is INSTRUMENT_ONLY is True
    assert spec["may_validate"] is MAY_VALIDATE is False
    assert spec["may_fund"] is MAY_FUND is False
    assert spec["may_merge"] is MAY_MERGE is False
    assert spec["may_auto_close_dead_ends"] is False
    assert spec["session_owner"] == "HarnessSession"
    assert spec["domain_door"] == "live_mcp"
    assert spec["project_id_env"] == PROJECT_ID_ENV
    assert "research_lead" in spec["suggested_roster_roles"]


def test_campaign_does_not_reuse_builtin_planner() -> None:
    imported = _imported_modules(HARNESS_ROOT / "campaign.py")
    assert "app.services.campaigns" not in imported
    assert "app.models.research_campaign" not in imported
    assert "app.agent" not in imported
    source = (HARNESS_ROOT / "campaign.py").read_text(encoding="utf-8")
    assert "start_campaign" not in source
    assert "AGENT_LOOP_ENABLED" not in source.split('"""', 2)[-1]


def test_session_owner_is_not_a_checkpoint_writer() -> None:
    for rel in ("session.py", "campaign.py", "gateway.py"):
        path = HARNESS_ROOT / rel
        imported = _imported_modules(path)
        assert "app.services.checkpoints" not in imported, rel
        assert "app.models.checkpoint" not in imported, rel
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = ""
                if isinstance(func, ast.Name):
                    name = func.id
                elif isinstance(func, ast.Attribute):
                    name = func.attr
                assert name != "Checkpoint", rel
                assert name != "create_checkpoint", rel


def test_harness_has_exactly_one_checkpoint_service_import() -> None:
    writers = []
    for path in HARNESS_ROOT.glob("*.py"):
        if "app.services.checkpoints" in _imported_modules(path):
            writers.append(path.name)
    assert writers == ["live_mcp.py"]


def test_session_from_env_unbound_without_project() -> None:
    assert session_from_env({}) is None
    bound = session_from_env({PROJECT_ID_ENV: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"})
    assert isinstance(bound, HarnessSession)
    assert str(bound.project_uuid) == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    assert bound.resolved_max_turns() == DEFAULT_MAX_TURNS
    assert bound.notes == SESSION_NOTES


def test_open_session_does_not_invent_an_actor() -> None:
    session = open_session("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", max_turns=2)
    assert session.extras["campaign"] == SLUG
    assert session.resolved_max_turns() == 2
    imported = _imported_modules(HARNESS_ROOT / "campaign.py")
    assert "app.models.actor" not in imported
    assert "app.models.account" not in imported
    assert "app.services.funding" not in imported


def test_extra_body_drops_models_and_route() -> None:
    body = build_fail_closed_body(
        model=DEFAULT_MODEL,
        messages=[{"role": "user", "content": "hi"}],
        extra={
            "provider": {"allow_fallbacks": True},
            "models": ["openai/gpt-4o"],
            "route": "fallback",
            "transforms": ["middle-out"],
            "temperature": 0.1,
        },
    )
    assert "models" not in body
    assert "route" not in body
    assert "transforms" not in body
    assert body["temperature"] == 0.1
    assert body["provider"]["allow_fallbacks"] is False
    assert "models" in REFUSED_EXTRA_BODY_KEYS
    assert "route" in REFUSED_EXTRA_BODY_KEYS
    assert "temperature" in ALLOWED_EXTRA_BODY_KEYS


def test_fixture_probe_log_uses_protocol_maybe_log() -> None:
    source = (HARNESS_ROOT / "fixture_mcp.py").read_text(encoding="utf-8")
    assert "from app.harness.protocol import" in source
    assert "write_message" in source
    assert "read_message" in source
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            assert node.name != "_maybe_log"
            assert node.name != "_write_message"


def test_gateway_version_is_fail_closed_composition_release() -> None:
    assert VERSION == "0.44.0"


def test_gateway_process_refuses_unmetered_without_flag() -> None:
    with pytest.raises(SystemExit, match="refusing unmetered gateway child"):
        assert_process_may_serve({})
    with pytest.raises(SystemExit, match=PROJECT_ID_ENV):
        require_bound_session({})


def test_gateway_process_allows_explicit_unmetered_probe() -> None:
    assert unmetered_probe_enabled({}) is False
    assert unmetered_probe_enabled({UNMETERED_PROBE_ENV: "1"}) is True
    assert assert_process_may_serve({UNMETERED_PROBE_ENV: "true"}) is None


def test_gateway_process_serves_when_session_owned() -> None:
    owned = assert_process_may_serve(
        {PROJECT_ID_ENV: "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"}
    )
    assert owned is not None
    assert str(owned.project_uuid) == "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
    campaign = require_bound_session(
        {PROJECT_ID_ENV: "ffffffff-ffff-ffff-ffff-ffffffffffff"}
    )
    assert str(campaign.project_uuid) == "ffffffff-ffff-ffff-ffff-ffffffffffff"


async def test_http_gateway_turn_cap_refuses_before_llm() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json=_OK_BODY)

    session = HarnessSession(
        project_id="cccccccc-cccc-cccc-cccc-cccccccccccc",
        max_turns=1,
        turn_index=1,
    )
    env = {GATEWAY_TOKEN_ENV: "gw-secret"}
    app = create_metered_gateway_app(session, env=env, gateway=_gateway(handler))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://gw") as client:
        refused = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer gw-secret"},
            json={"model": DEFAULT_MODEL, "messages": [{"role": "user", "content": "hi"}]},
        )
    assert refused.status_code == 422
    payload = refused.json()
    assert payload["refused"] is True
    assert payload["minted"] is False
    assert payload["tokens_used"] == 0
    assert payload["error"] == REASON_TURN_BUDGET
    assert calls["n"] == 0


async def test_health_reports_bound_session() -> None:
    env = {GATEWAY_TOKEN_ENV: "gw-secret"}
    unbound = create_gateway_app(env=env)
    async with AsyncClient(transport=ASGITransport(app=unbound), base_url="http://gw") as client:
        health = await client.get("/health")
    assert health.json()["session_owned"] is False
    assert health.json()["version"] == "0.44.0"

    session = open_session("dddddddd-dddd-dddd-dddd-dddddddddddd", max_turns=3)
    owned = create_metered_gateway_app(session, env=env)
    async with AsyncClient(transport=ASGITransport(app=owned), base_url="http://gw") as client:
        health = await client.get("/health")
    body = health.json()
    assert body["session_owned"] is True
    assert body["project_id"] == "dddddddd-dddd-dddd-dddd-dddddddddddd"
    assert body["max_turns"] == 3


def test_fastapi_boot_path_still_ignores_harness() -> None:
    for rel in ("app/main.py", "app/api/router.py"):
        source = (BACKEND_ROOT / rel).read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("app.harness"), rel
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("app.harness"), rel


def test_fly_toml_env_has_no_secrets() -> None:
    text = (BACKEND_ROOT / "fly.toml").read_text(encoding="utf-8")
    assigned: list[str] = []
    in_env = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "[env]":
            in_env = True
            continue
        if in_env and stripped.startswith("["):
            break
        if not in_env or not stripped or stripped.startswith("#"):
            continue
        key = stripped.split("=", 1)[0].strip().upper()
        assigned.append(key)
    for secret in (
        "OPENROUTER_API_KEY",
        "OPENTHEORY_GATEWAY_TOKEN",
        "OPENTHEORY_ACTOR_JWT",
        "OPENTHEORY_ACTOR_JWT_FILE",
        "DATABASE_URL",
        "AGENT_LOOP_ENABLED",
    ):
        assert secret not in assigned, secret


def test_session_from_env_rejects_non_uuid() -> None:
    with pytest.raises(Exception, match="must be a UUID"):
        session_from_env({PROJECT_ID_ENV: "not-a-uuid"})
