"""Generate, validate, retry once, then fall back (section 3.4).

Structure can be enforced; truth cannot. So after the model answers, the reply must parse
against the Answer schema and every citation must name a passage that was really
retrieved for this request. One retry, then a safe canned response. The user never sees a
500 because a model wrote prose instead of JSON.
"""

from __future__ import annotations

import logging
import time

import httpx

from .. import telemetry
from ..providers.llm.base import LLMProvider, ProviderError
from ..schemas import Answer, Citation, Passage

log = logging.getLogger("rahbar.generation")

ABSTAIN_TEXT = "The documents I have do not cover this question, so I cannot answer it."
FALLBACK_TEXT = ("I could not produce a reliable answer from the documents just now. "
                 "Please try again, or ask the relevant office.")


class UngroundedAnswer(ValueError):
    """The model claimed an answer but cited nothing that was retrieved."""


def abstention(reasoning: str) -> Answer:
    return Answer(reasoning=reasoning, answer=ABSTAIN_TEXT, citations=[],
                  answered_from_context=False, confidence="low")


def check_citations(answer: Answer, passages: list[Passage]) -> Answer:
    """Keep only citations that match a retrieved passage, and fill in the real page.

    An answer that claims to come from the documents but keeps no valid citation is
    rejected: a citation the retriever never returned is fabricated.
    """
    if not answer.answered_from_context:
        return answer.model_copy(update={"citations": []})
    retrieved = {(p.source, p.section): p for p in passages}
    valid: dict[tuple[str, str], Citation] = {}
    for citation in answer.citations:
        key = (citation.source, citation.section)
        if key in retrieved and key not in valid:
            valid[key] = Citation(source=key[0], section=key[1], page=retrieved[key].page)
    dropped = len(answer.citations) - len(valid)
    if dropped:
        telemetry.INVALID_CITATIONS.inc(dropped)
        log.warning("citations dropped", extra={"dropped": dropped})
    if not valid:
        raise UngroundedAnswer("the answer cites no passage that was retrieved")
    return answer.model_copy(update={"citations": list(valid.values())})


def generate_checked(provider: LLMProvider, question: str,
                     passages: list[Passage]) -> tuple[Answer, bool]:
    """Return (answer, used_fallback)."""
    started = time.perf_counter()
    try:
        for attempt in (1, 2):
            try:
                return check_citations(provider.generate(question, passages), passages), False
            except (ValueError, ProviderError, httpx.HTTPError) as exc:
                # ValueError covers pydantic's ValidationError, bad JSON and UngroundedAnswer
                log.warning("generation failed", extra={
                    "attempt": attempt, "error": type(exc).__name__, "detail": str(exc)[:200]})
        telemetry.FALLBACKS.inc()
        return Answer(reasoning="fallback after two failed attempts", answer=FALLBACK_TEXT,
                      citations=[], answered_from_context=False, confidence="low"), True
    finally:
        telemetry.GENERATION_SECONDS.observe(time.perf_counter() - started)