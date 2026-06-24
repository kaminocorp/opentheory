"""Bearer-JWT verification adapter (0.6.0).

The single, swappable seam between OpenTheory and an identity provider (Decision #2).
It turns an ``Authorization: Bearer <token>`` value into a verified
:class:`VerifiedIdentity` ``(subject, email, display_name)`` — nothing more. The backend
*only* verifies a JWT and reads claims; it does not couple domain logic to the Supabase
client. Swapping to Clerk/Auth0 (all JWT/JWKS-based) changes only this file + config; the
``ActingActor`` dependency, the ``Actor`` mapping, and every service stay identical.

Verification path: Supabase Auth signs the session token with HS256 using the project's
JWT secret, so we verify the signature, audience, and expiry against that shared secret.
``supabase_jwks_url`` is reserved as a forward hook for asymmetric (RS256/ES256) signing
keys; wiring it in is a config + this-module change, no caller change.
"""

from dataclasses import dataclass

import jwt

from app.core.config import settings


class AuthError(Exception):
    """Raised when a bearer token is missing, malformed, expired, or fails verification.

    The dependency layer maps this to HTTP ``401`` — it never leaks as a ``500``.
    """


@dataclass(frozen=True)
class VerifiedIdentity:
    """The minimal verified claims we map onto an ``Actor`` (Decision #1)."""

    subject: str  # the IdP subject (`sub`) — stored as Actor.external_id
    email: str | None
    display_name: str | None


def verify_bearer_token(token: str) -> VerifiedIdentity:
    """Verify a Supabase HS256 JWT and return its identity claims.

    Raises :class:`AuthError` on any verification failure (bad signature, expired,
    wrong audience, missing required claims, or auth not configured).
    """
    secret = settings.supabase_jwt_secret
    if not secret:
        # Defensive: in production auth must be configured. A request reaching here with a
        # bearer token but no configured secret is a misconfiguration, not an authz pass.
        raise AuthError("authentication is not configured (no Supabase JWT secret)")

    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
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
