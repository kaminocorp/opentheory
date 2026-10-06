"""Reference campaign for the external DeepSeek Harness path (0.43.0 / 0.44.0).

Odd perfect numbers. The **human** sets the research question, the
research-crew roster (``project.agent_models``), and the budget
(``FundingAllocation``). This module does not invent an ``Account``,
does not mint an ``Actor``, does not fund, does not validate, and does
not merge. Dead ends stay.

The campaign's only runtime job is to **own the session**: bind a
:class:`~app.harness.session.HarnessSession` to the human's project and
hand that owner to the fail-closed gateway the Cordis ``llm-pi-ai``
plugin actually calls. ``0.44.0`` makes this module the authored
composition child — it refuses to serve when unbound. Domain writes
stay on ``live_mcp`` → ``run_instrument`` / ``create_checkpoint``.

Does not light ``AGENT_LOOP_ENABLED``. Does not reuse
``ResearchCampaign``. FastAPI does not import this package. Fly does
not run this child.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.harness.gateway import create_gateway_app
from app.harness.session import (
    PROJECT_ID_ENV,
    HarnessSession,
    TurnRefused,
    session_from_env,
)
from app.schemas.project import AGENT_ROLE_FIELDS

SLUG = "odd-perfect-numbers"
TITLE = "Odd perfect numbers"
QUESTION = (
    "Does an odd perfect number exist? A perfect number equals the sum of "
    "its proper divisors. Even perfect numbers are classified by the "
    "Euclid–Euler theorem; no odd perfect number is known, and none has "
    "been ruled out."
)
BACKGROUND = (
    "Human-owned reference campaign on the external DeepSeek Harness path. "
    "The human sets this question, the research-crew roster "
    "(project.agent_models), and the ComputeDebit pot (FundingAllocation). "
    "The harness is instrument-only: run_instrument and create_checkpoint "
    "through the existing chokepoints. It never funds, never self-validates, "
    "and never merges. Abandoned lines stay on the ledger."
)
SUGGESTED_ROSTER_ROLES = AGENT_ROLE_FIELDS
INSTRUMENT_ONLY = True
MAY_VALIDATE = False
MAY_FUND = False
MAY_MERGE = False
MAY_AUTO_CLOSE_DEAD_ENDS = False


def reference_spec() -> dict[str, Any]:
    """Frozen description a human (or a test) uses to open the project."""
    return {
        "slug": SLUG,
        "title": TITLE,
        "question": QUESTION,
        "background": BACKGROUND,
        "suggested_roster_roles": list(SUGGESTED_ROSTER_ROLES),
        "instrument_only": INSTRUMENT_ONLY,
        "may_validate": MAY_VALIDATE,
        "may_fund": MAY_FUND,
        "may_merge": MAY_MERGE,
        "may_auto_close_dead_ends": MAY_AUTO_CLOSE_DEAD_ENDS,
        "session_owner": "HarnessSession",
        "domain_door": "live_mcp",
        "project_id_env": PROJECT_ID_ENV,
    }


def open_session(
    project_id: UUID | str,
    *,
    turn_index: int = 0,
    max_turns: int | None = None,
    daily_token_cap: int | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    env: Mapping[str, str] | None = None,
    actor_env: Mapping[str, str] | None = None,
) -> HarnessSession:
    """Bind the reference campaign to a human-created project.

    Does not create the project, the roster, the budget, or an Actor.
    Those are human writes through the existing APIs. ``actor_env``
    (JWT file / JWT / flagged dev-actor) is the actor ``authorize()``
    membership-checks — same injection as ``live_mcp``.
    """
    return HarnessSession(
        project_id=project_id,
        turn_index=turn_index,
        max_turns=max_turns,
        daily_token_cap=daily_token_cap,
        session_factory=session_factory,
        env=env,
        actor_env=actor_env,
        extras={"campaign": SLUG},
    )


def create_metered_gateway_app(
    session: HarnessSession,
    *,
    env: Mapping[str, str] | None = None,
    gateway: Any = None,
):
    """HTTP child the Cordis plugin points at — metering sits on this app."""
    return create_gateway_app(env=env, gateway=gateway, session=session)


def require_bound_session(
    env: Mapping[str, str] | None = None,
) -> HarnessSession:
    """Refuse to serve the campaign child when no project is bound."""
    try:
        session = session_from_env(env)
    except TurnRefused as exc:
        raise SystemExit(f"refusing campaign child — {exc.reason}") from exc
    if session is None:
        raise SystemExit(
            f"session=unbound ({PROJECT_ID_ENV} unset) — not starting gateway"
        )
    return session


def main() -> None:
    spec = reference_spec()
    print(f"campaign={spec['slug']}")
    print(f"title={spec['title']}")
    print(f"question={spec['question']}")
    print("instrument_only=true")
    print("may_validate=false may_fund=false may_merge=false")
    print(f"session_owner={spec['session_owner']}")
    print(f"domain_door={spec['domain_door']}")
    session = require_bound_session()
    print(
        f"session=owned project_id={session.project_uuid} "
        f"max_turns={session.resolved_max_turns()}"
    )
    import os

    import uvicorn

    host = os.environ.get("OPENTHEORY_GATEWAY_HOST", "127.0.0.1")
    port = int(os.environ.get("OPENTHEORY_GATEWAY_PORT", "8787"))
    uvicorn.run(create_metered_gateway_app(session), host=host, port=port)


if __name__ == "__main__":
    main()
