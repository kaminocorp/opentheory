"""DB-free tests for the account ``@username`` slice (0.8.3).

The pure helpers (``app/core/usernames.py``), the ``AccountUpdate`` schema validation
(normalize → pattern → reserved), and the ``PATCH /me`` auth gate (rejected by ``ActingActor``
*before* any DB access). All run in the default suite — no Postgres needed.
"""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import settings
from app.core.usernames import (
    USERNAME_PATTERN,
    base_from,
    generate_username_candidates,
    is_valid_username,
    normalize,
    with_suffix,
)
from app.schemas.account import AccountUpdate


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Hello World!", "hello_world"),
        ("  Jane.Doe  ", "jane_doe"),
        ("a.b..c", "a_b_c"),
        ("UPPER", "upper"),
        ("!!!", "user"),  # all-disallowed → fallback base
        ("", "user"),
        ("ab", "ab0"),  # too short → zero-padded to the 3-char minimum
        ("__weird__", "weird"),  # leading/trailing underscores trimmed
        ("a" * 40, "a" * 30),  # truncated to 30
        ("你好", "user"),  # non-ascii stripped → fallback
    ],
)
def test_normalize(raw: str, expected: str) -> None:
    assert normalize(raw) == expected


def test_normalize_output_always_matches_pattern() -> None:
    # Whatever goes in, normalize yields a string matching ^[a-z0-9_]{3,30}$ (charset + length).
    for raw in ["", "@@@", "x", "Hello, World!!!", "___", "a" * 100, "你好", "12", "  "]:
        assert USERNAME_PATTERN.match(normalize(raw)), raw


def test_base_from_prefers_email_local_part() -> None:
    assert base_from("Jane.Doe@example.com", "Jane Doe") == "jane_doe"


def test_base_from_falls_back_to_display_name_then_user() -> None:
    assert base_from(None, "Cool Person") == "cool_person"
    assert base_from(None, None) == "user"
    assert base_from("", "") == "user"


def test_base_from_skips_reserved_sources() -> None:
    # An email local-part that normalizes to a reserved word falls through to the display name…
    assert base_from("admin@example.com", "Real Name") == "real_name"
    # …and if every source is reserved/empty, the last-resort base is "user" (never reserved).
    assert base_from("admin@x.com", "system") == "user"


def test_with_suffix_stays_within_limit() -> None:
    out = with_suffix("a" * 30, "12")
    assert len(out) == 30
    assert out.endswith("12")


def test_generate_candidates_is_sequential() -> None:
    gen = generate_username_candidates("jane")
    assert [next(gen) for _ in range(4)] == ["jane", "jane2", "jane3", "jane4"]


def test_is_valid_username() -> None:
    assert is_valid_username("jane_doe")
    assert not is_valid_username("me")  # reserved
    assert not is_valid_username("Ab")  # uppercase + too short
    assert not is_valid_username("no spaces")


@pytest.mark.parametrize(
    "good, expected",
    [
        ("jane_doe", "jane_doe"),
        ("Foo", "foo"),  # lowercased
        ("  JANE  ", "jane"),  # trimmed + lowercased
        ("abc", "abc"),
        ("a_1", "a_1"),
        ("user", "user"),  # not reserved
    ],
)
def test_account_update_accepts_and_normalizes(good: str, expected: str) -> None:
    assert AccountUpdate(username=good).username == expected


@pytest.mark.parametrize(
    "bad",
    [
        "ab",  # too short
        "a" * 31,  # too long
        "Foo Bar",  # space (rename does not auto-slug — must already be valid)
        "foo-bar",  # hyphen not allowed
        "admin",  # reserved
        "ME",  # reserved after lowercasing
        "system",  # reserved
        "",  # empty
    ],
)
def test_account_update_rejects(bad: str) -> None:
    with pytest.raises(ValidationError):
        AccountUpdate(username=bad)


def test_unauthenticated_me_update_is_rejected(
    dbfree_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # PATCH /me (0.8.3) is auth-gated by ActingActor; an unauthenticated request is rejected before
    # the handler touches the DB. A *valid* body isolates the 401 to the auth gate (not validation).
    monkeypatch.setattr(settings, "auth_dev_header_enabled", False)

    resp = dbfree_client.patch("/api/v1/me", json={"username": "newhandle"})

    assert resp.status_code == 401, resp.text
