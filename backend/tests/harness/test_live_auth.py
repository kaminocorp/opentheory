"""Auth injection for the live MCP door — no bearer in logs."""

from __future__ import annotations

import json

import pytest
from fastapi import HTTPException

from app.harness.auth import (
    DEV_ACTOR_ENV,
    JWT_ENV,
    JWT_FILE_ENV,
    load_credential,
    redact,
)


def test_jwt_file_wins_over_env(tmp_path) -> None:
    token_path = tmp_path / "actor.jwt"
    token_path.write_text("file-token\n", encoding="utf-8")
    cred = load_credential(
        {
            JWT_FILE_ENV: str(token_path),
            JWT_ENV: "env-token",
            DEV_ACTOR_ENV: "should-not-win",
        }
    )
    assert cred is not None
    assert cred.kind == "jwt"
    assert cred.value == "file-token"
    assert cred.source == JWT_FILE_ENV
    assert "file-token" not in repr(cred)


def test_jwt_env_beats_dev_actor() -> None:
    cred = load_credential({JWT_ENV: "bearer-token", DEV_ACTOR_ENV: "actor-id"})
    assert cred is not None
    assert cred.kind == "jwt"
    assert cred.value == "bearer-token"


def test_dev_actor_is_last_resort() -> None:
    cred = load_credential({DEV_ACTOR_ENV: "actor-id"})
    assert cred is not None
    assert cred.kind == "dev_actor"
    assert cred.value == "actor-id"


def test_missing_credential_is_none() -> None:
    assert load_credential({}) is None


def test_empty_jwt_file_is_401(tmp_path) -> None:
    token_path = tmp_path / "empty.jwt"
    token_path.write_text("  \n", encoding="utf-8")
    with pytest.raises(HTTPException) as exc:
        load_credential({JWT_FILE_ENV: str(token_path)})
    assert exc.value.status_code == 401


def test_missing_jwt_file_is_401(tmp_path) -> None:
    with pytest.raises(HTTPException) as exc:
        load_credential({JWT_FILE_ENV: str(tmp_path / "nope.jwt")})
    assert exc.value.status_code == 401


def test_redact_strips_secret_keys() -> None:
    payload = {
        "params": {
            "env": {
                JWT_ENV: "super-secret-bearer",
                JWT_FILE_ENV: "/tmp/actor.jwt",
                "OPENTHEORY_PROBE_NONCE": "n-1",
            },
            "authorization": "Bearer super-secret-bearer",
        },
        "nested": [{JWT_ENV: "also-secret"}],
    }
    cleaned = redact(payload)
    dumped = json.dumps(cleaned)
    assert "super-secret-bearer" not in dumped
    assert "also-secret" not in dumped
    assert cleaned["params"]["env"][JWT_ENV] == "***"
    assert cleaned["params"]["authorization"] == "***"
    assert cleaned["params"]["env"]["OPENTHEORY_PROBE_NONCE"] == "n-1"
    # Path may be logged; the file contents must not.
    assert cleaned["params"]["env"][JWT_FILE_ENV] == "***"
