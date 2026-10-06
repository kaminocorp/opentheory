"""Agent definition catalog (0.59.0).

A versioned kind owned by an Account. Unique ``(family_id, version)``.
Cosmetic rename mutates the same row; a config-fingerprint change is a
new version. FastAPI may import this module. It must not import
``app.harness``. Write helpers ``db.add`` and never commit.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.actor import Actor
from app.models.agent_definition import AgentDefinition
from app.models.checkpoint import Checkpoint
from app.models.compute_debit import ComputeDebit
from app.models.project_agent_member import ProjectAgentMember
from app.models.validation import Validation
from app.schemas.agent_definition import (
    AgentDefinitionCreate,
    AgentDefinitionPatch,
    AgentDefinitionRead,
    AgentDefinitionVersionCreate,
    AgentFamilyActorRead,
    AgentFamilyRollupRead,
)
from app.services.harness_meter import is_daily_cap_adjustment

# Inputs that change the fingerprint. Extra config keys are stored for
# display but do not bump the version on their own.
CONFIG_FINGERPRINT_KEYS = ("model_id", "harness_pin", "cordis_inventory", "persona_hash")


def config_fingerprint(config: dict[str, Any]) -> str:
    canonical = {key: config.get(key) for key in CONFIG_FINGERPRINT_KEYS}
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def _read(row: AgentDefinition) -> AgentDefinitionRead:
    return AgentDefinitionRead.model_validate(row)


async def _owned(
    db: AsyncSession, definition_id: UUID, account_id: UUID
) -> AgentDefinition:
    row = await db.get(AgentDefinition, definition_id)
    if row is None or row.account_id != account_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent definition not found"
        )
    return row


async def get_definition(db: AsyncSession, definition_id: UUID) -> AgentDefinition | None:
    return await db.get(AgentDefinition, definition_id)


async def list_definitions(db: AsyncSession, account_id: UUID) -> list[AgentDefinitionRead]:
    result = await db.execute(
        select(AgentDefinition)
        .where(AgentDefinition.account_id == account_id)
        .order_by(AgentDefinition.family_id.asc(), AgentDefinition.version.asc())
    )
    return [_read(row) for row in result.scalars()]


async def create_definition(
    db: AsyncSession, account_id: UUID, payload: AgentDefinitionCreate
) -> AgentDefinitionRead:
    family_id = uuid4()
    row = AgentDefinition(
        account_id=account_id,
        family_id=family_id,
        version=1,
        display_name=payload.display_name.strip(),
        config=payload.config,
        config_fingerprint=config_fingerprint(payload.config),
    )
    db.add(row)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="that family version already exists",
        ) from exc
    return _read(row)


async def patch_definition(
    db: AsyncSession,
    definition_id: UUID,
    account_id: UUID,
    payload: AgentDefinitionPatch,
) -> AgentDefinitionRead:
    row = await _owned(db, definition_id, account_id)
    row.display_name = payload.display_name.strip()
    db.add(row)
    await db.flush()
    return _read(row)


async def create_version(
    db: AsyncSession,
    definition_id: UUID,
    account_id: UUID,
    payload: AgentDefinitionVersionCreate,
) -> AgentDefinitionRead:
    current = await _owned(db, definition_id, account_id)
    fingerprint = config_fingerprint(payload.config)
    if fingerprint == current.config_fingerprint:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="config fingerprint unchanged; PATCH the existing version for a cosmetic rename",
        )
    latest = await db.execute(
        select(func.max(AgentDefinition.version)).where(
            AgentDefinition.family_id == current.family_id
        )
    )
    next_version = int(latest.scalar_one() or current.version) + 1
    name = payload.display_name.strip() if payload.display_name else current.display_name
    row = AgentDefinition(
        account_id=account_id,
        family_id=current.family_id,
        version=next_version,
        display_name=name,
        config=payload.config,
        config_fingerprint=fingerprint,
    )
    db.add(row)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="that family version already exists",
        ) from exc
    return _read(row)


async def _family_visible(
    db: AsyncSession, family_id: UUID, acting_account_id: UUID | None, acting_id: UUID
) -> bool:
    owned = await db.execute(
        select(AgentDefinition.id)
        .where(
            AgentDefinition.family_id == family_id,
            AgentDefinition.account_id == acting_account_id,
        )
        .limit(1)
    )
    if owned.first() is not None:
        return True
    from app.services.project_members import ensure_is_member

    seats = await db.execute(
        select(ProjectAgentMember.project_id)
        .join(Actor, Actor.id == ProjectAgentMember.actor_id)
        .join(AgentDefinition, AgentDefinition.id == Actor.agent_definition_id)
        .where(AgentDefinition.family_id == family_id)
    )
    seen: set[UUID] = set()
    for (project_id,) in seats:
        if project_id in seen:
            continue
        seen.add(project_id)
        try:
            acting = await db.get(Actor, acting_id)
            if acting is None:
                return False
            await ensure_is_member(db, project_id, acting)
            return True
        except HTTPException:
            continue
    return False


async def get_readable_definition(
    db: AsyncSession, definition_id: UUID, acting: Actor
) -> AgentDefinitionRead:
    row = await db.get(AgentDefinition, definition_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent definition not found"
        )
    if not await _family_visible(db, row.family_id, acting.account_id, acting.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent definition not found"
        )
    return _read(row)


async def family_rollup(
    db: AsyncSession, family_id: UUID, acting: Actor
) -> AgentFamilyRollupRead:
    if not await _family_visible(db, family_id, acting.account_id, acting.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent family not found"
        )
    versions_result = await db.execute(
        select(AgentDefinition)
        .where(AgentDefinition.family_id == family_id)
        .order_by(AgentDefinition.version.asc())
    )
    versions = list(versions_result.scalars())
    if not versions:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent family not found"
        )
    version_ids = [row.id for row in versions]
    version_by_id = {row.id: row for row in versions}

    actors_result = await db.execute(
        select(Actor).where(Actor.agent_definition_id.in_(version_ids))
    )
    actors = list(actors_result.scalars())
    actor_ids = [actor.id for actor in actors]

    actor_reads: list[AgentFamilyActorRead] = []
    for actor in actors:
        project_raw = (actor.actor_metadata or {}).get("project_id")
        project_id: UUID | None
        try:
            project_id = UUID(str(project_raw)) if project_raw else None
        except ValueError:
            project_id = None
        definition = version_by_id.get(actor.agent_definition_id)  # type: ignore[arg-type]
        actor_reads.append(
            AgentFamilyActorRead(
                actor_id=actor.id,
                project_id=project_id,
                display_name=actor.display_name,
                definition_id=actor.agent_definition_id,  # type: ignore[arg-type]
                definition_version=definition.version if definition is not None else 0,
            )
        )

    checkpoint_count = 0
    validation_count = 0
    tokens_billed = 0
    amount_billed = Decimal("0")
    if actor_ids:
        checkpoint_count = int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(Checkpoint)
                    .where(Checkpoint.author_id.in_(actor_ids))
                )
            ).scalar_one()
        )
        authored = select(Checkpoint.id).where(Checkpoint.author_id.in_(actor_ids))
        validation_count = int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(Validation)
                    .where(Validation.checkpoint_id.in_(authored))
                )
            ).scalar_one()
        )
        debit_rows = await db.execute(
            select(ComputeDebit.tokens_used, ComputeDebit.amount, ComputeDebit.notes).where(
                ComputeDebit.actor_id.in_(actor_ids)
            )
        )
        for tokens_used, amount, notes in debit_rows:
            if tokens_used <= 0 or is_daily_cap_adjustment(notes):
                continue
            tokens_billed += int(tokens_used)
            amount_billed += Decimal(amount)

    return AgentFamilyRollupRead(
        family_id=family_id,
        versions=[_read(row) for row in versions],
        actors=actor_reads,
        checkpoints_authored=checkpoint_count,
        incoming_validations=validation_count,
        tokens_billed=tokens_billed,
        amount_billed=amount_billed,
    )
