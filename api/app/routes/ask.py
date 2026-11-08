"""POST /api/ask. The Ingress sends /api/* here unchanged, so the prefix stays."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, Response

from ..retrieval.base import RetrievalError
from ..schemas import AskRequest, AskResponse
from ..services.answer import answer_question

log = logging.getLogger("rahbar.ask")

router = APIRouter(prefix="/api")


@router.post("/ask", response_model=AskResponse)
def ask(body: AskRequest, request: Request, response: Response) -> AskResponse:
    state = request.app.state
    try:
        result = answer_question(body.question, state.retriever, state.provider, state.cache,
                                 state.settings, follow_up=body.follow_up)
    except RetrievalError as exc:
        log.error("retrieval unavailable", extra={"error": str(exc)})
        raise HTTPException(
            status_code=503,
            detail="The document index is unavailable. Please try again shortly.") from exc
    if state.cache.enabled:
        response.headers["X-Cache"] = "hit" if result.cached else "miss"
    return result