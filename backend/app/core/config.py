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

    @field_validator("backend_cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str] | str | list[AnyHttpUrl]:
        if isinstance(value, str) and value:
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
