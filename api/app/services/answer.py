"""Turns a question into an AskResponse: the query pipeline of section 3.2.

    1 validate (the request schema)      5 augment (in the provider)
    2 cache check                        6 generate
    3 embed (inside the retriever)       7 validate, retry once, fall back
    4 retrieve, then the relevance floor 8 cache the answer if it is safe to cache

Each step lives in its own module so it can be tested alone. The API is stateless, so
"store the turn" is the request log line and the cache entry.
"""

from __future__ import annotations

import logging
import time

from .. import telemetry
from .. import ragops
from ..providers.llm.prompt import build_messages
from ..config import Settings
from ..logjson import request_id_var
from ..providers.llm.base import LLMProvider
from ..retrieval.base import RetrievalError, Retriever
from ..schemas import AskResponse, RetrievedRef
from .cache import Cache, never_cache
from .generation import abstention, generate_checked

log = logging.getLogger("rahbar.answer")


def _cache_scope(retriever: Retriever, cache: Cache, follow_up: bool) -> str | None:
    """The index_id to cache under, or None when this request must not use the cache."""
    if not cache.enabled:
        return None
    if follow_up:
        telemetry.CACHE_LOOKUPS.labels("skipped").inc()
        return None
    try:
        return retriever.index_info().index_id
    except RetrievalError:
        return None


def answer_question(
    question: str, retriever: Retriever, provider: LLMProvider, cache: Cache,
    settings: Settings, follow_up: bool = False, eval_request: bool = False,
) -> AskResponse:
    cache_started = time.perf_counter()
    index_id = _cache_scope(retriever, cache, follow_up or eval_request)
    ragops.update(cache='bypass' if eval_request else 'miss')
    if index_id is not None:
        hit = cache.lookup(question, index_id)
        telemetry.CACHE_LOOKUPS.labels("hit" if hit else "miss").inc()
        if hit is not None:
            try:
                original = ragops.read_trace(hit.request_id)
                ragops.update(context=original['context'], generation_attempts=[],
                              prompt_hash=original['prompt_hash'], cache_source_trace=hit.request_id)
            except FileNotFoundError:
                ragops.update(cache_context_unavailable=True)
            ragops.update(cache='hit', response=hit.answer, citations=[c.model_dump() for c in hit.citations],
                          answered_from_context=hit.answered_from_context,
                          retrieved=[r.model_dump() for r in hit.retrieved])
            ragops.stage('cache', cache_started)
            log.info("answered", extra={"cached": True, "top_k": settings.top_k,
                                        "answered_from_context": hit.answered_from_context,
                                        "abstained": not hit.answered_from_context,
                                        "scores": [r.score for r in hit.retrieved],
                                        "chunk_ids": [r.chunk_id for r in hit.retrieved]})
            return hit.model_copy(update={"request_id": request_id_var.get()})

    ragops.stage('cache', cache_started)

    started = time.perf_counter()
    passages = retriever.retrieve(question, k=settings.top_k)
    telemetry.RETRIEVAL_SECONDS.observe(time.perf_counter() - started)
    ragops.stage('retrieve_including_embed', started)
    if passages:
        ragops.TOP1.observe(passages[0].score)
    ragops.update(retrieved=[{**p.model_dump(), 'document_id': p.source} for p in passages],
                  reranked_order=[p.chunk_id for p in passages])

    usable = [p for p in passages if p.score >= settings.relevance_floor
              and not ragops.flag(p.text, p.chunk_id)]
    ragops.update(context=[p.model_dump() for p in usable])
    fallback = False
    generated = time.perf_counter()
    if usable:
        if provider.name == 'stub':
            ragops.attempt(build_messages(question, usable), 'stub', {'seed': settings.seed})
        answer, fallback = generate_checked(provider, question, usable)
    else:
        answer = abstention("nothing retrieved cleared the relevance floor")
    ragops.stage('generate_and_validate', generated)
    abstained = not answer.answered_from_context and not fallback
    if abstained:
        telemetry.ABSTENTIONS.inc()

    response = AskResponse(
        request_id=request_id_var.get(), answer=answer.answer, citations=answer.citations,
        answered_from_context=answer.answered_from_context, confidence=answer.confidence,
        retrieved=[RetrievedRef(chunk_id=p.chunk_id, source=p.source, section=p.section,
                                page=p.page, score=p.score, doc_version=p.doc_version,
                                superseded=p.superseded) for p in passages],
        provider=provider.name)
    ragops.update(response=response.answer, citations=[c.model_dump() for c in response.citations],
                  answered_from_context=response.answered_from_context, fallback=fallback)
    if index_id is not None and not never_cache(response, fallback=fallback, follow_up=follow_up):
        cache.store(question, index_id, response)

    log.info("answered", extra={
        "retriever": retriever.name, "provider": provider.name, "top_k": settings.top_k,
        "chunk_ids": [p.chunk_id for p in passages],
        "scores": [round(p.score, 4) for p in passages],
        "relevance_floor": settings.relevance_floor, "usable": len(usable),
        "answered_from_context": answer.answered_from_context,
        "abstained": abstained, "fallback": fallback, "cached": False})
    return response
