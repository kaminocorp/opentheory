from decimal import Decimal
from functools import lru_cache
from typing import Annotated

from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "local"
    app_name: str = "OpenTheory API"
    api_v1_prefix: str = "/api/v1"
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/opentheory"
    )
    # Optional separate connection for Alembic migrations. The app runs over the Supabase
    # transaction pooler (:6543), but DDL + schema introspection prefer a stable, non-pooled
    # session, so migrations use this direct/session URL when set. Falls back to database_url.
    migration_database_url: str | None = None
    # NoDecode: skip pydantic-settings' default JSON decoding of this complex (list) field so
    # the comma-splitting validator below receives the raw env string (e.g. "http://a,http://b")
    # instead of crashing on json.loads. Without it, a non-JSON BACKEND_CORS_ORIGINS env value
    # raises before any validator runs.
    backend_cors_origins: Annotated[list[AnyHttpUrl], NoDecode] = []

    # --- Auth (0.6.0; ES256/JWKS since 0.7.x) --------------------------------------
    # Supabase Auth issues the session JWT; the backend only verifies it and reads claims
    # (Decision #2). Supabase now signs sessions with ES256 (asymmetric) and publishes the
    # public keys at the project's JWKS endpoint, so verification fetches the signing key by
    # `kid` from there — there is no shared secret. Set supabase_project_url (the JWKS URL is
    # derived from it) or supabase_jwks_url to override the endpoint directly.
    supabase_jwks_url: str | None = None
    supabase_project_url: str | None = None
    # The expected `aud` claim. Supabase signs signed-in users with aud="authenticated".
    supabase_jwt_audience: str = "authenticated"
    # When True, the X-Dev-Actor-Id header path stays active (local + tests). In production
    # this is False and only a verified bearer token is accepted (api/deps.py).
    auth_dev_header_enabled: bool = False
    # Emails granted the `internal` role on JIT provisioning — gates native funding
    # (Decision #4). Comma-split like backend_cors_origins; compared case-insensitively.
    internal_actor_emails: Annotated[list[str], NoDecode] = []

    # --- Toolbench execution sandbox (0.11.x) -----------------------------------------
    # Wall-clock cap for instrument runs (sync subprocess and async retrieval).
    toolbench_wall_timeout_s: float = 30.0
    # Child-process memory ceiling via RLIMIT_AS (Linux prod). 0 = disabled — default locally
    # because RLIMIT_AS is unreliable on macOS dev; set 256 on Fly (see docs/operations/deploy.md).
    toolbench_memory_limit_mb: int = 0
    # Max concurrent instrument runs per API process; excess waiters get 503 after acquire timeout.
    toolbench_max_concurrent_runs: int = 2
    # How long a run may wait for a concurrency slot before returning 503.
    toolbench_acquire_timeout_s: float = 5.0
    # When False, sync instruments run in-thread (fast unit tests only); production keeps True.
    toolbench_subprocess_sandbox_enabled: bool = True
    # Soft timeout for Z3's *internal* solver clock (ms). Must stay strictly below
    # toolbench_wall_timeout_s so a hard problem returns unknown→undecided (recorded) rather
    # than being killed by the subprocess wall-clock (mints nothing). The wall-clock/RLIMIT_AS
    # remain the hard backstop if a pathological case ignores the soft timeout.
    toolbench_z3_timeout_ms: int = 10_000
    # Soft timeout for ``interval.eval`` (ms). Must stay strictly below
    # toolbench_wall_timeout_s so a pathological enclosure records honest
    # undecided rather than a sandbox kill that mints nothing. python-flint
    # is a locked wheel; if the C extension fails to import the instrument
    # degrades to mpmath.iv, then to undecided — never a fabricated bound.
    toolbench_interval_timeout_ms: int = 8_000
    # Soft timeout for a ``lean.prove`` typecheck (ms). Must stay strictly below
    # toolbench_wall_timeout_s so a slow snippet records honest undecided rather
    # than a sandbox kill that mints nothing. Lean is optional: a missing binary
    # is undecided/unavailable, not a boot failure.
    toolbench_lean_timeout_ms: int = 8_000
    # Soft timeout for ``lean.prove`` with mathlib=true (ms). Mathlib oleans load
    # is slower than prelude; still clamped under the wall. Missing lake/Mathlib
    # is undecided/mathlib_unavailable, not a boot failure.
    toolbench_lean_mathlib_timeout_ms: int = 20_000
    # Optional path to a pre-built Mathlib lake project (lakefile + .lake cache).
    # Empty → conventional /opt/opentheory/lean-mathlib or OPENTHEORY_MATHLIB_LAKE.
    # Do not point this at a skeleton without oleans — that cannot earn Grade A.
    toolbench_mathlib_lake: str | None = None
    # Contact address embedded in the outbound User-Agent for Crossref's polite pool (and
    # as courtesy on arXiv / OpenAlex). Not a secret. Empty → UA without mailto.
    toolbench_retrieval_mailto: str | None = None
    # Optional OpenAlex key. The works endpoint still answers a small unauthenticated demo
    # pool; production agent loops should set this. Never required to boot the process —
    # a missing key is not a startup failure, and tests inject a Fetcher so they never need
    # one. As of Feb 2026 the polite-pool mailto param is ignored; the key is the real quota.
    openalex_api_key: str | None = None

    # --- Thin agent loop (0.12.x / 0.20.0) --------------------------------------------
    # The agent loop turns the config-only Research crew into an operator: a bounded
    # plan → observe → replan loop (OpenRouter) of *existing* instrument runs on an agent
    # branch, through the same chokepoint humans use.
    #
    # NOTE on caps: these are SAFETY limits (they bound a single pass's blast radius), NOT
    # project budget. Real budget is the *project-level* ceiling shipped in `0.19.0`
    # (historically `0.12.5`; never per-thread). These caps remain the blast-radius bound
    # on top of that ceiling. Prod enablement is an ops flip, not a code change:
    # `OPENROUTER_API_KEY` is a Fly **secret** (`fly secrets set`), never `fly.toml [env]`;
    # `AGENT_LOOP_ENABLED` is the dark-launch flag production sets when the key is in place
    # (see docs/operations/deploy.md). Do not invent a second key or a second flag.
    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # Wall-clock cap for one planning / replan call.
    agent_llm_timeout_s: float = 60.0
    # Max instrument attempts a single pass may execute (landed or failed; safety, not budget).
    agent_pass_max_runs: int = 5
    # Max *additional* planning calls after the initial plan (0 = one-shot, the 0.12.x shape).
    # Default 2 → at most 3 LLM calls per pass (initial + two replans).
    agent_pass_max_replans: int = 2
    # Max runnable steps one plan version may propose. Keeps the first batch short so there is
    # remaining run budget to spend after observing. The orchestrator also slices to this.
    agent_pass_max_batch_runs: int = 2
    # Token ceiling for a pass's planning calls — still a SAFETY cap (blast radius), recorded
    # on the trace. The project ceiling that turns those tokens into spend is
    # ``agent_token_rate_usd_per_1k`` × tokens, debited in 0.19.0, or the live
    # OpenRouter prompt/completion rates when 0.28.0 metering can fetch them.
    agent_pass_max_tokens: int = 200_000
    # Default blended USD per 1 000 planning tokens. Used when live OpenRouter
    # prices are unavailable (missing key, timeout, fetch failure, unknown model)
    # or when ``openrouter_live_prices`` is off. A catalog ``ModelOption.usd_per_1k``
    # still overrides this per model on the fallback path. Snapshot onto each
    # ``ComputeDebit`` so a later rate change never rewrites history.
    agent_token_rate_usd_per_1k: Decimal = Decimal("0.005")
    # 0.28.0 — live OpenRouter model prices for ComputeDebit. Off = always use the
    # blended fallback (still meters; never skips). Tests disable this in conftest
    # so a local OPENROUTER_API_KEY cannot reach the network.
    openrouter_live_prices: bool = True
    # Process-local cache of GET /models. A refresh is one short HTTP call; a
    # pass never waits longer than ``openrouter_price_timeout_s``.
    openrouter_price_cache_ttl_s: float = 3600.0
    # Hard cap on one price-catalog fetch. Keep this tiny relative to
    # ``agent_llm_timeout_s`` — a slow /models must not stall a planning call.
    openrouter_price_timeout_s: float = 2.0
    # Dark-launch flag: when False the agent-run, orchestration, *and* campaign
    # routes 404 (indistinguishable from "not a route"). One flag for the whole
    # agent family — do not invent a second. Campaigns are the continuous outer
    # loop over the 0.22.0 orchestrator; they reuse this gate.
    agent_loop_enabled: bool = False
    # Hard cap on how many ``run_agent_pass`` calls one orchestration may commission.
    # Per-pass safety caps and the 0.19.0 project ceiling still bind each sub-pass.
    orchestration_max_passes: int = 4
    # How many of those sub-passes may run at once (0.27.0). Default 2; ``1`` is the
    # sequential fallback. Clamped to ``ORCHESTRATION_CONCURRENCY_HARD_CAP`` (8) so
    # a typo cannot fan out a process. Each concurrent pass reserves a slice of
    # ``project_budget.available`` before it starts so they cannot oversell the pot.
    orchestration_concurrency: int = 2
    # Hard cap on how many 0.22.0 orchestrations one continuous campaign may
    # commission. Safety, not a second dark-launch flag. Default 8.
    campaign_max_cycles: int = 8
    # How many of those orchestrations may run at once (0.32.0). Default 1 is
    # today's sequential campaign. Clamped to
    # ``CAMPAIGN_CYCLE_CONCURRENCY_HARD_CAP`` (4). Concurrent cycle starts still
    # serialize on the project-row reservation lock so they cannot oversell.
    campaign_cycle_concurrency: int = 1
    # Consecutive failed cycles after which a campaign stops (error budget).
    campaign_error_budget: int = 3

    @field_validator("backend_cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str] | str | list[AnyHttpUrl]:
        if isinstance(value, str) and value:
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("internal_actor_emails", mode="before")
    @classmethod
    def parse_internal_emails(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [email.strip().lower() for email in value.split(",") if email.strip()]
        return [email.strip().lower() for email in value]

    @property
    def jwks_url(self) -> str | None:
        """The Supabase JWKS endpoint used to fetch ES256 verification keys.

        Prefers an explicit ``supabase_jwks_url``; otherwise derives the standard endpoint from
        ``supabase_project_url`` (``<url>/auth/v1/.well-known/jwks.json``). ``None`` when neither
        is configured — auth then rejects every bearer token (api/core/auth.py).
        """
        if self.supabase_jwks_url:
            return self.supabase_jwks_url
        if self.supabase_project_url:
            return f"{self.supabase_project_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
        return None


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
