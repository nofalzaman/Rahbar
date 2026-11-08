"""Validation, the single retry, the safe fallback and the citation check."""

from __future__ import annotations

import httpx
import pytest
from pydantic import ValidationError

from app.providers.llm.base import ProviderError
from app.schemas import Citation
from app.services.generation import (
    FALLBACK_TEXT,
    UngroundedAnswer,
    check_citations,
    generate_checked,
)
from tests.fakes import ScriptedProvider, good_answer, passage


def bad_json() -> ValidationError:
    try:
        from app.providers.llm.prompt import parse_answer
        parse_answer("not json at all")
    except ValidationError as exc:
        return exc
    raise AssertionError("expected a validation error")


def test_a_good_answer_passes_through_with_its_citation() -> None:
    p = passage()
    answer, fallback = generate_checked(ScriptedProvider(good_answer(p)), "q?", [p])
    assert fallback is False
    assert [(c.source, c.section) for c in answer.citations] == [("rules.md", "1. Attendance")]


def test_a_citation_the_retriever_never_returned_is_dropped() -> None:
    p = passage()
    made_up = Citation(source="made-up.pdf", section="9.9 Invented", page=4)
    real = Citation(source=p.source, section=p.section, page=99)
    checked = check_citations(good_answer(p, citations=[made_up, real]), [p])
    assert [(c.source, c.section) for c in checked.citations] == [(p.source, p.section)]
    assert checked.citations[0].page == p.page           # the model's wrong page is corrected


def test_an_answer_with_only_fabricated_citations_is_rejected() -> None:
    p = passage()
    fake = good_answer(p, citations=[Citation(source="x.pdf", section="1", page=1)])
    with pytest.raises(UngroundedAnswer):
        check_citations(fake, [p])


def test_an_answer_that_cites_nothing_is_rejected() -> None:
    p = passage()
    with pytest.raises(UngroundedAnswer):
        check_citations(good_answer(p, citations=[]), [p])


def test_an_honest_abstention_keeps_no_citations() -> None:
    p = passage()
    abstained = good_answer(p, answered_from_context=False,
                            citations=[Citation(source="x", section="y")])
    assert check_citations(abstained, [p]).citations == []


def test_one_bad_reply_is_retried_and_the_second_is_used() -> None:
    p = passage()
    provider = ScriptedProvider(bad_json(), good_answer(p))
    answer, fallback = generate_checked(provider, "q?", [p])
    assert (fallback, len(provider.calls), answer.answered_from_context) == (False, 2, True)


@pytest.mark.parametrize("failure", [
    bad_json(), ProviderError("odd shape"), httpx.ReadTimeout("slow"),
    httpx.HTTPStatusError("429", request=httpx.Request("POST", "http://x"),
                          response=httpx.Response(429)),
])
def test_two_failures_give_the_canned_response_never_an_exception(failure: Exception) -> None:
    provider = ScriptedProvider(failure, failure)
    answer, fallback = generate_checked(provider, "q?", [passage()])
    assert fallback is True
    assert len(provider.calls) == 2
    assert (answer.answer, answer.answered_from_context, answer.citations) == (
        FALLBACK_TEXT, False, [])


def test_an_ungrounded_answer_twice_also_falls_back() -> None:
    p = passage()
    ungrounded = good_answer(p, citations=[])
    answer, fallback = generate_checked(ScriptedProvider(ungrounded, ungrounded), "q?", [p])
    assert fallback is True and answer.answer == FALLBACK_TEXT