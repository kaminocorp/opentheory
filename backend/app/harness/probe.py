"""Probe: composition always; live OpenRouter only when opted in (0.42.0).

Default CI must stay green without ``OPENROUTER_API_KEY``, a ``dsh`` binary,
or the optional ``[harness]`` extra. A live gateway round-trip is skip, not
fail, unless ``OPENTHEORY_HARNESS_LIVE`` is set *and* a token is present.
The live path is the fail-closed OpenRouter gateway — it does not boot
``dsh`` and does not require the SDK extra.
"""

from __future__ import annotations

import asyncio
import os
import shutil
from dataclasses import dataclass
from typing import Any

from app.harness.composition import VERSION, verify
from app.harness.fixture_mcp import assert_inventory

LIVE_FLAG = "OPENTHEORY_HARNESS_LIVE"
GATEWAY_TOKEN_ENV = "OPENTHEORY_GATEWAY_TOKEN"
OPENROUTER_KEY_ENV = "OPENROUTER_API_KEY"
DSH_BINARIES = ("dsh", "deepseek-harness")


@dataclass(frozen=True)
class ProbeReport:
    composition: str
    fixture: str
    live: str
    skipped_live: bool


def composition_ok() -> None:
    verify()


def fixture_ok() -> None:
    assert_inventory()


def live_probe_skip_reason(
    env: dict[str, str] | None = None,
    *,
    dsh_on_path: bool | None = None,
    sdk_importable: bool | None = None,
) -> str | None:
    """Return a skip reason, or ``None`` if a live gateway probe may run.

    ``dsh_on_path`` / ``sdk_importable`` are accepted for call-site stability
    (0.40.0) but no longer gate the OpenRouter path — the gateway is OT code.
    """
    del dsh_on_path, sdk_importable
    lookup = env if env is not None else os.environ
    flag = lookup.get(LIVE_FLAG, "").strip().lower()
    if flag not in {"1", "true", "yes"}:
        return f"{LIVE_FLAG} is unset — live OpenRouter probe is opt-in"
    has_token = bool(
        lookup.get(GATEWAY_TOKEN_ENV, "").strip() or lookup.get(OPENROUTER_KEY_ENV, "").strip()
    )
    if not has_token:
        return f"no {OPENROUTER_KEY_ENV} / {GATEWAY_TOKEN_ENV}"
    return None


def dsh_available() -> bool:
    return any(shutil.which(name) for name in DSH_BINARIES)


def harness_sdk_available() -> bool:
    try:
        import importlib

        importlib.import_module("deepseek_harness_sdk")
        return True
    except ImportError:
        return False


async def run_live_gateway_probe(
    *,
    transport: Any = None,
    gateway: Any = None,
    env: dict[str, str] | None = None,
) -> str:
    """One fail-closed OpenRouter completion. Used only after skip-reason is None."""
    from app.harness.gateway import DEFAULT_MODEL, GatewayClient, resolve_model

    verify()
    client = gateway or GatewayClient(transport=transport, env=env)
    model = resolve_model(env=env)
    response = await client.complete(
        model=model or DEFAULT_MODEL,
        messages=[{"role": "user", "content": "Reply with the single word pong."}],
        max_tokens=16,
    )
    return f"ok tokens={response.tokens_used} model={response.model}"


def run_probe(*, live_transport: Any = None, live_gateway: Any = None) -> ProbeReport:
    """Always assert composition + fixture. Live is skip unless opted in."""
    composition_ok()
    fixture_ok()
    reason = live_probe_skip_reason()
    if reason is not None:
        return ProbeReport(
            composition="ok",
            fixture="ok",
            live=f"skipped: {reason}",
            skipped_live=True,
        )
    live = asyncio.run(
        run_live_gateway_probe(transport=live_transport, gateway=live_gateway)
    )
    return ProbeReport(
        composition="ok",
        fixture="ok",
        live=live,
        skipped_live=False,
    )


def main() -> None:
    report = run_probe()
    print(f"composition={report.composition}")
    print(f"fixture={report.fixture}")
    print(f"live={report.live}")
    print(f"sdk_pin={VERSION}")
    print(f"dsh={dsh_available()} sdk={harness_sdk_available()}")


if __name__ == "__main__":
    main()
