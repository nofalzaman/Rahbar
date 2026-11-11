"""The query pipeline end to end with fakes: floor, abstention, grounding and the cache."""

from __future__ import annotations

from typing import Any

import pytest
from prometheus_client import REGISTRY

from app.config import Settings
from app.logjson import request_id_var
from app.retrieval.base import RetrievalError
from app.schemas import Citation
from app.services import cache as cache_module
from app.services.answer import answer_question
from app.services.cache import NullCache, RedisCache
from app.services.generation import ABSTAIN_TEXT, FALLBACK_TEXT
from tests.fakes import FakeRedis, FakeRetriever, ScriptedProvider, good_answer, passage

SETTINGS = Settings(retriever="chroma", relevance_floor=0.35, top_k=5)


def counter(name: str, **labels: str) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


@pytest.fixture
def live_cache(monkeypatch: Any) -> tuple[RedisCache, FakeRedis]:
    vectors = {"attendance?": [1.0, 0.0], "attendance rule?": [0.99, 0.14], "fees?": [0.0, 1.0]}
    monkeypatch.setattr(cache_module, "embed_query", lambda settings, q: vectors[q])
    client = FakeRedis()
    return RedisCache(client, Settings(retriever="chroma", cache_threshold=0.95)), client


def test_a_grounded_answer_cites_a_retrieved_passage_and_lists_what_was_retrieved() -> None:
    p = passage(score=0.8)
    response = answer_question("attendance?", FakeRetriever([p]),
                               ScriptedProvider(good_answer(p)), NullCache(), SETTINGS)
    assert response.answered_from_context is True
    assert [(c.source, c.section) for c in response.citations] == [(p.source, p.section)]
    assert [r.chunk_id for r in response.retrieved] == [p.chunk_id]
    assert response.cached is False


def test_nothing_above_the_floor_abstains_without_calling_the_model() -> None:
    weak = passage(score=0.10)
    provider = ScriptedProvider()                      # would raise IndexError if called
    before = counter("rahbar_abstentions_total")
    response = answer_question("hostel rules?", FakeRetriever([weak]), provider,
                               NullCache(), SETTINGS)
    assert provider.calls == []
    assert (response.answered_from_context, response.answer, response.citations) == (
        False, ABSTAIN_TEXT, [])
    assert [r.chunk_id for r in response.retrieved] == [weak.chunk_id]   # still reported
    assert counter("rahbar_abstentions_total") == before + 1


def test_only_passages_above_the_floor_reach_the_model() -> None:
    strong, weak = passage("1. A", score=0.8), passage("2. B", score=0.2, chunk_id="doc-2")
    provider = ScriptedProvider(good_answer(strong))
    response = answer_question("q?", FakeRetriever([strong, weak]), provider,
                               NullCache(), SETTINGS)
    assert [p.chunk_id for p in provider.calls[0][1]] == [strong.chunk_id]
    assert len(response.retrieved) == 2


def test_the_model_declining_is_an_abstention_with_no_citations() -> None:
    p = passage()
    declined = good_answer(p, answered_from_context=False, answer="Not covered.")
    response = answer_question("q?", FakeRetriever([p]), ScriptedProvider(declined),
                               NullCache(), SETTINGS)
    assert (response.answered_from_context, response.citations) == (False, [])


def test_a_model_that_keeps_failing_gives_the_fallback_not_a_500() -> None:
    p = passage()
    before = counter("rahbar_fallbacks_total")
    provider = ScriptedProvider(RuntimeError("never caught?"), RuntimeError("x"))
    with pytest.raises(RuntimeError):                  # only expected failures are absorbed
        answer_question("q?", FakeRetriever([p]), provider, NullCache(), SETTINGS)
    junk = good_answer(p, citations=[Citation(source="nope", section="nope")])
    response = answer_question("q?", FakeRetriever([p]), ScriptedProvider(junk, junk),
                               NullCache(), SETTINGS)
    assert (response.answer, response.answered_from_context) == (FALLBACK_TEXT, False)
    assert counter("rahbar_fallbacks_total") == before + 1


def test_the_second_ask_of_a_similar_question_is_a_cache_hit(
        live_cache: tuple[RedisCache, FakeRedis]) -> None:
    cache, _ = live_cache
    p = passage()
    retriever = FakeRetriever([p])
    provider = ScriptedProvider(good_answer(p))
    token = request_id_var.set("req-2")
    try:
        first = answer_question("attendance?", retriever, provider, cache, SETTINGS)
        second = answer_question("attendance rule?", retriever, provider, cache, SETTINGS)
    finally:
        request_id_var.reset(token)
    assert (first.cached, second.cached) == (False, True)
    assert second.answer == first.answer and second.request_id == "req-2"
    assert len(provider.calls) == 1 and retriever.retrieve_calls == 1


def test_abstentions_fallbacks_and_follow_ups_are_never_cached(
        live_cache: tuple[RedisCache, FakeRedis]) -> None:
    cache, client = live_cache
    p, weak = passage(), passage(score=0.1)
    answer_question("attendance?", FakeRetriever([weak]), ScriptedProvider(), cache, SETTINGS)
    junk = good_answer(p, citations=[])
    answer_question("attendance?", FakeRetriever([p]), ScriptedProvider(junk, junk),
                    cache, SETTINGS)
    skipped = counter("rahbar_cache_lookups_total", result="skipped")
    answer_question("attendance?", FakeRetriever([p]), ScriptedProvider(good_answer(p)),
                    cache, SETTINGS, follow_up=True)
    assert counter("rahbar_cache_lookups_total", result="skipped") == skipped + 1
    assert [k for k in client.values if ":entry:" in k] == []


def test_a_reindex_invalidates_the_cache(live_cache: tuple[RedisCache, FakeRedis]) -> None:
    cache, _ = live_cache
    p = passage()
    retriever = FakeRetriever([p])
    provider = ScriptedProvider(good_answer(p), good_answer(p))
    answer_question("attendance?", retriever, provider, cache, SETTINGS)
    retriever.info = retriever.info.__class__(count=5, embed_model="nomic-embed-text",
                                              index_id="idx-2")     # the indexer ran again
    again = answer_question("attendance?", retriever, provider, cache, SETTINGS)
    assert again.cached is False and len(provider.calls) == 2


def test_an_unreachable_index_raises_retrieval_error_for_the_route_to_turn_into_503() -> None:
    retriever = FakeRetriever([passage()])
    retriever.error = RetrievalError("chroma is down")
    with pytest.raises(RetrievalError):
        answer_question("q?", retriever, ScriptedProvider(), NullCache(), SETTINGS)