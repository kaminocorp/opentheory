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
    # Emails granted the `internal` (Kamino) role on JIT provisioning — gates native funding
    # (Decision #4). Comma-split like backend_cors_origins; compared case-insensitively.
    internal_actor_emails: Annotated[list[str], NoDecode] = []

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
