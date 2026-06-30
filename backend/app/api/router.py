from fastapi import APIRouter

from app.api.routes import (
    accounts,
    actors,
    agent_models,
    branches,
    checkpoints,
    claims,
    evidence,
    funding,
    health,
    invitations,
    me,
    projects,
    threads,
    validations,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(me.router, tags=["auth"])
api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(actors.router, prefix="/actors", tags=["actors"])
api_router.include_router(accounts.router, prefix="/accounts", tags=["accounts"])
# Threads/claims/evidence/checkpoints span nested paths (e.g. /projects/{id}/threads
# and /threads/{id}), so they mount at the root and declare full paths themselves.
api_router.include_router(threads.router)
api_router.include_router(claims.router)
api_router.include_router(evidence.router)
api_router.include_router(checkpoints.router)
api_router.include_router(validations.router)
api_router.include_router(branches.router)
api_router.include_router(funding.router)
# Invitations span /projects/{id}/invitations and /me/invitations + /invitations/{id}/…, so the
# router mounts at the root and declares full paths itself (like threads/funding).
api_router.include_router(invitations.router)
# Agent-model catalog is a root-level, project-less read (/agent-models/catalog).
api_router.include_router(agent_models.router, tags=["agent-models"])
