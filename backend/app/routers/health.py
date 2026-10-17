from __future__ import annotations

from fastapi import APIRouter

from .. import __version__

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    """Liveness probe (used by the Docker healthcheck)."""
    return {"status": "ok", "service": "sitescope-api", "version": __version__}
