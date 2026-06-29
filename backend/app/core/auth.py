"""Bearer-JWT verification adapter (0.6.0; ES256/JWKS since 0.7.x).

The single, swappable seam between OpenTheory and an identity provider (Decision #2).
It turns an ``Authorization: Bearer <token>`` value into a verified
:class:`VerifiedIdentity` ``(subject, email, display_name)`` — nothing more. The backend
*only* verifies a JWT and reads claims; it does not couple domain logic to the Supabase
client. Swapping to Clerk/Auth0 (all JWT/JWKS-based) changes only this file + config; the
``ActingActor`` dependency, the ``Actor`` mapping, and every service stay identical.

Verification path: Supabase Auth now signs the session token with **ES256** (asymmetric)
using the project's current signing key, and publishes the matching public keys at the
project's JWKS endpoint. We fetch the signing key for the token's ``kid`` from there and
verify the signature, audience, and expiry against it — there is no shared secret to hold.
(The legacy HS256 shared-secret path was retired when Supabase moved to asymmetric keys.)
"""

import logging
import ssl
from dataclasses import dataclass
from functools import lru_cache

import certifi
import jwt
from jwt import PyJWKClient

from app.core.config import settings

logger = logging.getLogger(__name__)


class AuthError(Exception):
    """Raised when a bearer token is missing, malformed, expired, or fails verification.

    The dependency layer maps this to HTTP ``401`` — it never leaks as a ``500``.
    """


@dataclass(frozen=True)
class VerifiedIdentity:
    """The minimal verified claims we map onto an ``Actor`` (Decision #1)."""

    subject: str  # the IdP subject (`sub`) — stored as Account.external_id
    email: str | None
    display_name: str | None


@lru_cache(maxsize=1)
def _ssl_context() -> ssl.SSLContext:
    """A TLS context that verifies against the ``certifi`` CA bundle, not the OS trust store.

    The JWKS fetch is the backend's only outbound HTTPS call (Postgres uses asyncpg
    ``ssl=require``, which doesn't verify a CA), so we can't assume the container's
    ``/etc/ssl/certs`` is populated — certifi makes verification deterministic across local dev
    and the slim production image.
    """
    return ssl.create_default_context(cafile=certifi.where())


@lru_cache(maxsize=4)
def _jwks_client(url: str) -> PyJWKClient:
    """A process-cached JWKS client for ``url``.

    Cached by URL so the fetched key set is reused across requests: only the first
    authenticated request after a cold start (and a key rotation, after ``lifespan``) pays the
    network round-trip to the JWKS endpoint. ``cache_keys`` additionally memoizes the resolved
    per-``kid`` signing key. The fetch is synchronous; at this app's traffic the rare blocking
    cold-start fetch is acceptable and keeps the verifier's simple sync contract.
    """
    return PyJWKClient(url, cache_keys=True, lifespan=600, ssl_context=_ssl_context())


def _signing_key(token: str) -> object:
    """Resolve the public key to verify ``token`` with, by its ``kid``, from the JWKS endpoint.

    A seam the tests monkeypatch to inject a local key without network I/O. Raises
    :class:`AuthError` if auth is unconfigured, the endpoint is unreachable, or no key matches
    the token's ``kid``.
    """
    url = settings.jwks_url
    if not url:
        # Defensive: in production auth must be configured. A request reaching here with a
        # bearer token but no configured JWKS endpoint is a misconfiguration, not an authz pass.
        raise AuthError("authentication is not configured (no Supabase JWKS/project URL)")
    try:
        return _jwks_client(url).get_signing_key_from_jwt(token).key
    except jwt.PyJWTError as exc:
        # Covers a malformed token header, no matching `kid`, and (PyJWKClientConnectionError)
        # an unreachable JWKS endpoint — all of which subclass PyJWTError.
        raise AuthError(f"could not resolve signing key: {exc}") from exc


def prewarm_jwks() -> None:
    """Best-effort startup warm-up: fetch and cache the JWKS key set ahead of any traffic.

    Called from the app lifespan (in a worker thread, since the fetch is synchronous). It turns
    the first authenticated request from a blocking network round-trip into an in-memory cache
    hit. A no-op when auth is unconfigured, and it swallows a transient fetch failure — warming
    must never prevent the app from starting, and ``_signing_key`` still falls back to a lazy
    fetch on the request path if this didn't populate the cache.
    """
    url = settings.jwks_url
    if not url:
        return
    try:
        _jwks_client(url).get_jwk_set(refresh=True)
    except Exception as exc:  # best-effort: a brief JWKS outage must not block startup
        logger.warning("JWKS warm-up failed at startup: %s", exc)


def verify_bearer_token(token: str) -> VerifiedIdentity:
    """Verify a Supabase ES256 JWT and return its identity claims.

    Raises :class:`AuthError` on any verification failure (bad signature, expired,
    wrong audience, missing required claims, unresolvable signing key, or auth not configured).
    """
    signing_key = _signing_key(token)  # AuthError propagates (it is not a PyJWTError)
    try:
        claims = jwt.decode(
            token,
            signing_key,
            algorithms=["ES256"],
            audience=settings.supabase_jwt_audience,
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise AuthError(f"invalid token: {exc}") from exc

    subject = claims.get("sub")
    if not subject:
        raise AuthError("token is missing the `sub` claim")

    email = claims.get("email")
    # Display name: Supabase carries user-supplied profile fields under user_metadata; fall
    # back to email, then the subject, so display_name is always populated.
    user_metadata = claims.get("user_metadata") or {}
    display_name = (
        user_metadata.get("name")
        or user_metadata.get("full_name")
        or email
        or subject
    )
    return VerifiedIdentity(subject=str(subject), email=email, display_name=display_name)
