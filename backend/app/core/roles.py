"""Role constants + predicates for queryable authorization (0.6.0).

Roles live in ``actors.roles`` (a queryable column, Decision #4). Kept in ``core`` so both
the API dependency layer (``api/deps.py``) and the service layer (``services/funding.py``)
can share them without the service importing upward from the API layer.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.actor import Actor

# The Kamino (internal) role. Gates native funding (Decision #4) and is the substrate for
# validator/agent permissions later.
INTERNAL_ROLE = "internal"


def actor_is_internal(actor: "Actor") -> bool:
    return INTERNAL_ROLE in (actor.roles or [])
