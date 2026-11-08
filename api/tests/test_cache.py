"""The semantic cache: threshold, index-id invalidation, bounds and a dead Redis."""

from __future__ import annotations

from typing import Any

import pytest

from app.config import Settings
from app.schemas import AskResponse, RetrievedRef
from app.services import cache as cache_module
from app.services.cache import NullCache, RedisCache, get_cache, never_cache
from tests.fakes import FakeRedis

VECTORS = {
    "attendance?": [1.0, 0.0],
    "attendance rule?": [0.99, 0.14],      # cosine about 0.99 with the first
    "fees?": [0.0, 1.0],                   # cosine 0 with the first
}


def response() -> AskResponse:
    return AskResponse(
        request_id="req-1", answer="80 percent.", citations=[], answered_from_context=True,
        confidence="high", provider="x", cached=False,
        retrieved=[RetrievedRef(chunk_id="c1", source="r.md", section="1", page=1, score=0.9)])


@pytest.fixture
def setup(monkeypatch: Any) -> tuple[RedisCache, FakeRedis]:
    monkeypatch.setattr(cache_module, "embed_query", lambda settings, question: VECTORS[question])
    client = FakeRedis()
    return RedisCache(client, Settings(cache_threshold=0.95, cache_max_entries=2)), client


def test_a_similar_question_hits_and_a_different_one_misses(
        setup: tuple[RedisCache, FakeRedis]) -> None:
    cache, _ = setup
    cache.store("attendance?", "idx-1", response())
    hit = cache.lookup("attendance rule?", "idx-1")
    assert hit is not None and hit.cached is True and hit.answer == "80 percent."
    assert hit.retrieved[0].chunk_id == "c1"
    assert cache.lookup("fees?", "idx-1") is None


def test_the_threshold_decides(setup: tuple[RedisCache, FakeRedis]) -> None:
    cache, client = setup
    cache.store("attendance?", "idx-1", response())
    strict = RedisCache(client, Settings(cache_threshold=0.999))
    assert strict.lookup("attendance rule?", "idx-1") is None
    assert cache.lookup("attendance rule?", "idx-1") is not None


def test_a_new_index_id_makes_every_old_entry_miss(
        setup: tuple[RedisCache, FakeRedis]) -> None:
    cache, _ = setup
    cache.store("attendance?", "idx-1", response())
    assert cache.lookup("attendance?", "idx-1") is not None
    assert cache.lookup("attendance?", "idx-2") is None        # the index was rebuilt


def test_entries_expire_and_the_cache_stays_bounded(
        setup: tuple[RedisCache, FakeRedis]) -> None:
    cache, client = setup
    for question in VECTORS:
        cache.store(question, "idx-1", response())
    assert client.zcard("rahbar:cache:idx-1:ids") == 2          # cache_max_entries
    assert len([k for k in client.values if ":entry:" in k]) == 2
    assert set(client.ttls.values()) == {86400}


def test_an_expired_entry_is_forgotten_not_returned(
        setup: tuple[RedisCache, FakeRedis]) -> None:
    cache, client = setup
    cache.store("attendance?", "idx-1", response())
    client.values.clear()                                       # Redis expired the entry
    assert cache.lookup("attendance?", "idx-1") is None
    assert client.zcard("rahbar:cache:idx-1:ids") == 0


def test_a_dead_redis_is_a_miss_not_an_error(setup: tuple[RedisCache, FakeRedis]) -> None:
    cache, client = setup
    client.down = True
    assert cache.lookup("attendance?", "idx-1") is None
    cache.store("attendance?", "idx-1", response())              # must not raise
    with pytest.raises(Exception, match="down"):
        cache.ping()                                             # readiness does need the truth


def test_the_cache_is_off_without_redis_or_with_the_stub_retriever() -> None:
    assert isinstance(get_cache(Settings(retriever="stub", redis_url="redis://r:6379/0")),
                      NullCache)
    assert isinstance(get_cache(Settings(retriever="chroma", redis_url="")), NullCache)
    assert get_cache(Settings(retriever="chroma", redis_url="redis://r:6379/0")).enabled


def test_the_never_cache_rule() -> None:
    answered = response()
    declined = answered.model_copy(update={"answered_from_context": False})
    assert never_cache(answered, fallback=False, follow_up=False) is False
    assert never_cache(answered, fallback=False, follow_up=True) is True      # follow-up
    assert never_cache(answered, fallback=True, follow_up=False) is True      # failed validation
    assert never_cache(declined, fallback=False, follow_up=False) is True     # abstention