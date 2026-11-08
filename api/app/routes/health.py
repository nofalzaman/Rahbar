"""Liveness and readiness (section 4.3). They answer different questions."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request, Response

from ..services.readiness import check_readiness

log = logging.getLogger("rahbar.health")

router = APIRouter()


@router.get("/healthz")
def healthz() -> dict[str, str]:
    """Is the process alive? Must never touch Chroma, Redis or the LLM."""
    return {"status": "alive"}


@router.get("/readyz")
def readyz(request: Request, response: Response) -> dict[str, object]:
    """Can this pod take traffic? 503 names the dependency that failed (sections 4.3, 4.4)."""
    state = request.app.state
    result = check_readiness(state.settings, state.retriever, state.cache)
    status = (result.ready, result.failed)
    if status != state.last_readiness:
        state.last_readiness = status
        if result.ready:
            log.info("ready", extra={"checks": result.checks})
        else:
            log.error("not ready", extra={"failed": result.failed, "detail": result.detail})
    if result.ready:
        return {"status": "ready", "checks": result.checks}
    response.status_code = 503
    return {"status": "not ready", "failed": result.failed, "detail": result.detail,
            "checks": result.checks}