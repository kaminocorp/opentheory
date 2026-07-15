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

    # --- Thin agent loop (0.12.x) -----------------------------------------------------
    # The agent loop turns the config-only Research crew into an operator: one bounded planning
    # call (OpenRouter) → a validated, capped sequence of *existing* instrument runs on an agent
    # branch, through the same chokepoint humans use.
    #
    # NOTE on caps: `agent_pass_max_runs` / `agent_pass_max_tokens` are SAFETY limits (they bound
    # a single pass's blast radius), NOT budget. Real budget is a *project-level* concern wired in
    # 0.12.5 (never per-thread). `OPENROUTER_API_KEY` is a Fly **secret** (`fly secrets set`), never
    # `fly.toml [env]`; `AGENT_LOOP_ENABLED` is the dark-launch flag production flips when ready.
    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # Wall-clock cap for the single planning call (the one LLM round-trip per pass).
    agent_llm_timeout_s: float = 60.0
    # Max instrument runs a single pass may execute (safety, not budget).
    agent_pass_max_runs: int = 5
    # Token ceiling for a pass's planning call — recorded today, NOT yet enforced (the single
    # planning call is already bounded by agent_llm_timeout_s + the planner's own completion cap; a
    # real comparison against recorded usage lands with the project budget in 0.12.5).
    agent_pass_max_tokens: int = 200_000
    # Dark-launch flag: when False the agent-run routes 404 (indistinguishable from "not a route").
    agent_loop_enabled: bool = False

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
