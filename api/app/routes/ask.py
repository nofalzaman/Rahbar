"""POST /api/ask. The Ingress sends /api/* here unchanged, so the prefix stays."""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, HTTPException, Request, Response

from ..retrieval.base import RetrievalError
from ..schemas import AskRequest, AskResponse
from ..services.answer import answer_question
from .. import ragops

log = logging.getLogger("rahbar.ask")

router = APIRouter(prefix="/api")


@router.post("/ask", response_model=AskResponse)
def ask(body: AskRequest, request: Request, response: Response) -> AskResponse:
    state = request.app.state
    ragops.update(user_query=body.question, embedding_model=state.settings.embed_model,
                  embedding_version=os.environ.get('EMBED_VERSION', state.settings.embed_model),
                  collection=state.settings.collection,
                  model=state.settings.llm_model,
                  model_version=os.environ.get('LLM_VERSION', state.settings.llm_model),
                  deployment={'collection': state.settings.collection, 'model': state.settings.embed_model,
                              'top_k': state.settings.top_k, 'image': os.environ.get('RELEASE_IMAGE', 'unknown')},
                  parameters={'temperature': state.settings.temperature, 'seed': state.settings.seed,
                              'num_predict': 512})
    try:
        result = answer_question(body.question, state.retriever, state.provider, state.cache,
                                 state.settings, follow_up=body.follow_up,
                                 eval_request=request.headers.get('X-RAGOps-Eval') == '1')
    except RetrievalError as exc:
        log.error("retrieval unavailable", extra={"error": str(exc)})
        raise HTTPException(
            status_code=503,
            detail="The document index is unavailable. Please try again shortly.") from exc
    if state.cache.enabled:
        response.headers["X-Cache"] = "hit" if result.cached else "miss"
    return result


@router.get('/traces/{trace_id}')
def get_trace(trace_id: str) -> dict:
    """Local demo inspection endpoint: traces contain document text and user questions."""
    try:
        return ragops.read_trace(trace_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, 'trace not found') from exc
