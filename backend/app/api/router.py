from fastapi import APIRouter

from app.api.routes import actors, claims, evidence, health, projects, threads

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(actors.router, prefix="/actors", tags=["actors"])
# Threads/claims/evidence span nested paths (e.g. /projects/{id}/threads and
# /threads/{id}), so they mount at the root and declare full paths themselves.
api_router.include_router(threads.router)
api_router.include_router(claims.router)
api_router.include_router(evidence.router)
