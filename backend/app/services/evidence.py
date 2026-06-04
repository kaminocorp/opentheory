from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.claim import Claim
from app.models.evidence import Evidence
from app.models.links import ClaimEvidenceLink
from app.schemas.evidence import EvidenceCreate, EvidenceRead

# Authoritative validation of relation_kind lives here (the column is a plain VARCHAR;
# the Pydantic Literal is a convenience that mirrors this set).
RELATION_KINDS: frozenset[str] = frozenset({"support", "weaken", "context"})


def _to_read(evidence: Evidence, relation_kind: str, link_id: UUID) -> EvidenceRead:
    return EvidenceRead(
        id=evidence.id,
        project_id=evidence.project_id,
        thread_id=evidence.thread_id,
        title=evidence.title,
        source_type=evidence.source_type,
        uri=evidence.uri,
        retrieved_at=evidence.retrieved_at,
        content_hash=evidence.content_hash,
        citation=evidence.citation,
        notes=evidence.notes,
        evidence_metadata=evidence.evidence_metadata,
        relation_kind=relation_kind,  # type: ignore[arg-type]
        link_id=link_id,
        created_at=evidence.created_at,
        updated_at=evidence.updated_at,
    )


async def attach_evidence(
    db: AsyncSession, claim_id: UUID, payload: EvidenceCreate
) -> EvidenceRead:
    if payload.relation_kind not in RELATION_KINDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"relation_kind must be one of {sorted(RELATION_KINDS)}",
        )

    claim = await db.get(Claim, claim_id)
    if claim is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Claim not found",
        )

    evidence_fields = payload.model_dump(exclude={"relation_kind"})
    # Evidence inherits the claim's project/thread context.
    evidence = Evidence(
        project_id=claim.project_id,
        thread_id=claim.thread_id,
        **evidence_fields,
    )
    db.add(evidence)
    await db.flush()  # assign evidence.id before linking

    link = ClaimEvidenceLink(
        claim_id=claim.id,
        evidence_id=evidence.id,
        relation_kind=payload.relation_kind,
    )
    db.add(link)
    await db.commit()
    await db.refresh(evidence)
    await db.refresh(link)
    return _to_read(evidence, link.relation_kind, link.id)


async def list_evidence(db: AsyncSession, claim_id: UUID) -> list[EvidenceRead]:
    result = await db.execute(
        select(Evidence, ClaimEvidenceLink.relation_kind, ClaimEvidenceLink.id)
        .join(ClaimEvidenceLink, ClaimEvidenceLink.evidence_id == Evidence.id)
        .where(ClaimEvidenceLink.claim_id == claim_id)
        .order_by(ClaimEvidenceLink.created_at.desc())
    )
    return [
        _to_read(evidence, relation_kind, link_id)
        for evidence, relation_kind, link_id in result
    ]
