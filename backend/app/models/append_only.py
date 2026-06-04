"""Append-only enforcement for ledger primitives.

``Checkpoint``, ``CheckpointRef``, and ``FundingAllocation`` are append-only: once
written they are never updated or deleted (see CLAUDE.md / docs/primitives.md, which
name both ``Checkpoint`` and ``FundingAllocation`` as append-only). We enforce this at
the ORM layer (not merely "there is no endpoint") so the invariant holds even if the
route layer is bypassed — corrections, reversals, and retractions must be *new* records,
never edits. ``FundingAllocation`` has no write path yet, so the guard is dormant but in
place ahead of one landing.

The guards fire on ORM ``before_update`` / ``before_delete`` mapper events, i.e. when a
tracked instance is flushed as dirty or deleted. Bulk Core ``UPDATE``/``DELETE`` and DDL
(``drop_all`` in tests) bypass the ORM unit-of-work and are intentionally not covered
here — application writes all go through the ORM, which is the surface we protect.

Note: because this blocks ORM deletes, an ORM-level cascade delete of a ``Project`` would
be refused for its checkpoints. That is by design (append-only wins over cascade); there
is no project-delete path in 0.3.x.
"""

from typing import Any

from sqlalchemy import event

from app.models.checkpoint import Checkpoint
from app.models.funding import FundingAllocation
from app.models.links import CheckpointRef


class AppendOnlyError(Exception):
    """Raised when code attempts to UPDATE or DELETE an append-only ledger row."""


_APPEND_ONLY_MODELS = (Checkpoint, CheckpointRef, FundingAllocation)


def _block_mutation(mapper: Any, connection: Any, target: Any) -> None:
    raise AppendOnlyError(
        f"{type(target).__name__} is append-only; updates and deletes are not permitted"
    )


def register_append_only_guards() -> None:
    """Idempotently attach the update/delete guards to the append-only models."""
    for model in _APPEND_ONLY_MODELS:
        if not event.contains(model, "before_update", _block_mutation):
            event.listen(model, "before_update", _block_mutation)
        if not event.contains(model, "before_delete", _block_mutation):
            event.listen(model, "before_delete", _block_mutation)


register_append_only_guards()
