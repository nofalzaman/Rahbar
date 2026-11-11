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


MIN_PREFIX = 4  # a cited section must share at least this many characters with a real one


class UngroundedAnswer(ValueError):
    """The model claimed an answer but cited nothing that was retrieved."""


def abstention(reasoning: str) -> Answer:
    return Answer(reasoning=reasoning, answer=ABSTAIN_TEXT, citations=[],
                  answered_from_context=False, confidence="low")


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


def find_passage(citation: Citation, passages: list[Passage]) -> Passage | None:
    """The retrieved passage a citation points at, or None if it points at nothing.

    Section labels can be long, and a small model often copies only the start of one. So a
    citation also matches when one section is a prefix of the other (at least MIN_PREFIX
    characters) within the same source. It is still always a passage that was retrieved.
    """
    wanted = _norm(citation.section)
    same_source = [p for p in passages if p.source == citation.source]
    for passage in same_source:
        if _norm(passage.section) == wanted:
            return passage
    if len(wanted) < MIN_PREFIX:
        return None
    for passage in same_source:
        have = _norm(passage.section)
        if have.startswith(wanted) or wanted.startswith(have):
            return passage
    return None


def check_citations(answer: Answer, passages: list[Passage]) -> Answer:
    """Keep only citations that match a retrieved passage, and fill in the real section
    and page.

    An answer that claims to come from the documents but keeps no valid citation is
    rejected: a citation the retriever never returned is fabricated.
    """
    if not answer.answered_from_context:
        return answer.model_copy(update={"citations": [],
                                         "answer": answer.answer.strip() or ABSTAIN_TEXT})
    valid: dict[tuple[str, str], Citation] = {}
    for citation in answer.citations:
        passage = find_passage(citation, passages)
        if passage is not None:
            valid.setdefault((passage.source, passage.section), Citation(
                source=passage.source, section=passage.section, page=passage.page))
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
                raw = provider.generate(question, passages)
                log.info("model verdict", extra={
                    "attempt": attempt, "answered_from_context": raw.answered_from_context,
                    "confidence": raw.confidence, "citations": len(raw.citations),
                    "reasoning": raw.reasoning[:300]})
                return check_citations(raw, passages), False
            except (ValueError, ProviderError, httpx.HTTPError) as exc:
                # ValueError covers pydantic's ValidationError, bad JSON and UngroundedAnswer
                log.warning("generation failed", extra={
                    "attempt": attempt, "error": type(exc).__name__, "detail": str(exc)[:200]})
        telemetry.FALLBACKS.inc()
        return Answer(reasoning="fallback after two failed attempts", answer=FALLBACK_TEXT,
                      citations=[], answered_from_context=False, confidence="low"), True
    finally:
        telemetry.GENERATION_SECONDS.observe(time.perf_counter() - started)
