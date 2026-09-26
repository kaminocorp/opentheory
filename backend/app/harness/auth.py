"""MCP actor credentials — JWT file preferred; never log the bearer.

The live plugin is a stdio child. Putting a bearer on a tool argument or in
Cordis ``env: OPENTHEORY_ACTOR_JWT`` would leak it into session / probe logs
the next time someone dumps the process environment or the MCP config.

Chosen injection pattern (``0.41.0``):

1. **Preferred.** Parent writes the member-scoped JWT to a ``0600`` file and
   passes only ``OPENTHEORY_ACTOR_JWT_FILE`` (a path). Cordis may log the
   path. The child reads the file at resolve time and never echoes the
   contents.
2. **Accepted, never logged.** ``OPENTHEORY_ACTOR_JWT`` for a process that
   is *not* going through session-logged Cordis config (local experiments).
   Redacted from every probe-log payload.
3. **Local / tests only.** ``OPENTHEORY_DEV_ACTOR_ID`` maps to the existing
   ``X-Dev-Actor-Id`` resolver, and only when ``auth_dev_header_enabled`` is
   on. Production (flag off) is ``401``.

Resolution is the same ``ActingActor`` path humans use: verified bearer →
Account → primary ``human`` Actor, or the flagged dev-id escape hatch.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import resolve_actor_from_bearer, resolve_actor_from_dev_id
from app.models.actor import Actor

JWT_ENV = "OPENTHEORY_ACTOR_JWT"
JWT_FILE_ENV = "OPENTHEORY_ACTOR_JWT_FILE"
DEV_ACTOR_ENV = "OPENTHEORY_DEV_ACTOR_ID"
GATEWAY_TOKEN_ENV = "OPENTHEORY_GATEWAY_TOKEN"
OPENROUTER_KEY_ENV = "OPENROUTER_API_KEY"

# Keys whose values must never appear in probe / session logs.
SECRET_ENV_KEYS = frozenset(
    {JWT_ENV, JWT_FILE_ENV, DEV_ACTOR_ENV, GATEWAY_TOKEN_ENV, OPENROUTER_KEY_ENV}
)
_REDACTED = "***"


@dataclass(frozen=True)
class McpCredential:
    """A resolved credential handle. ``value`` is omitted from ``repr``."""

    kind: str  # "jwt" | "dev_actor"
    value: str
    source: str

    def __repr__(self) -> str:
        return f"McpCredential(kind={self.kind!r}, source={self.source!r}, value={_REDACTED})"


def load_credential(env: Mapping[str, str] | None = None) -> McpCredential | None:
    """Read the injection env. Does not verify the token and does not log it."""
    lookup = env if env is not None else os.environ
    path = (lookup.get(JWT_FILE_ENV) or "").strip()
    if path:
        try:
            token = read_jwt_file(path)
        except OSError as exc:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "Authentication required",
            ) from exc
        if not token:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
        return McpCredential(kind="jwt", value=token, source=JWT_FILE_ENV)
    token = (lookup.get(JWT_ENV) or "").strip()
    if token:
        return McpCredential(kind="jwt", value=token, source=JWT_ENV)
    actor_id = (lookup.get(DEV_ACTOR_ENV) or "").strip()
    if actor_id:
        return McpCredential(kind="dev_actor", value=actor_id, source=DEV_ACTOR_ENV)
    return None


def read_jwt_file(path: str) -> str:
    """Read a JWT file; strip whitespace. Exists so tests can stub I/O."""
    with open(path, encoding="utf-8") as handle:
        return handle.read().strip()


async def resolve_mcp_actor(
    db: AsyncSession, env: Mapping[str, str] | None = None
) -> Actor:
    """Resolve the acting Actor the same way FastAPI does. Never logs the bearer."""
    credential = load_credential(env)
    if credential is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Authentication required",
        )
    if credential.kind == "jwt":
        return await resolve_actor_from_bearer(db, credential.value)
    return await resolve_actor_from_dev_id(db, credential.value)


def redact(value: Any) -> Any:
    """Recursively drop secret env values from a log payload."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, nested in value.items():
            if str(key) in SECRET_ENV_KEYS or str(key).lower() in {
                "authorization",
                "bearer",
                "token",
                "jwt",
                "api_key",
                "apikey",
                "gateway_token",
            }:
                out[str(key)] = _REDACTED
            else:
                out[str(key)] = redact(nested)
        return out
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str) and _looks_like_secret_env_dump(value):
        return _REDACTED
    return value


def _looks_like_secret_env_dump(value: str) -> bool:
    """True when a log line is literally ``KEY=secret`` for a secret env name."""
    if "=" not in value:
        return False
    key, _sep, _rest = value.partition("=")
    return key.strip() in SECRET_ENV_KEYS
