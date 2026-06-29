"""Role constants + predicates for queryable authorization (0.6.0; account-aware in 0.7.0).

Roles live on ``accounts.roles`` (Decision #4) — they describe the *principal* (the owning
human/org), not a specific action identity, so they moved off ``actors`` with the
Account-owns-Actor change. Kept in ``core`` so both the API dependency layer (``api/deps.py``)
and the service layer (``services/funding.py``) can share them without the service importing
upward from the API layer.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.account import Account
    from app.models.actor import Actor

# The Kamino (internal) role. Gates native funding (Decision #4) and is the substrate for
# validator/agent permissions later. Lives on the Account now.
INTERNAL_ROLE = "internal"


def account_is_internal(account: "Account | None") -> bool:
    """The principal-level predicate. ``None`` (an account-less actor) is never internal."""
    return account is not None and INTERNAL_ROLE in (account.roles or [])


def actor_is_internal(actor: "Actor") -> bool:
    """Convenience: walk an actor to its owning principal and check there.

    Requires ``actor.account`` to be loaded — it is eager-loaded by ``_resolve_or_provision``
    (the single resolution path), so callers in the request flow read it synchronously. An
    account-less actor (``system`` / dev-bootstrap) has no principal and is therefore not internal.
    """
    return account_is_internal(actor.account)
