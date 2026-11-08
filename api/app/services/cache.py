"""The semantic cache (section 3.3): a repeated question, however it is phrased, is
answered from Redis instead of by the model.

Plain Redis has no vector search, so entries hold a normalised embedding and the lookup
compares them in Python. The cache is small (cache_max_entries) so that stays cheap.

Entries live under the index_id the indexer wrote into the collection metadata. A
re-index gives the new collection a new index_id, so every old entry stops matching
without the indexer ever touching Redis.

Never cached: follow-up questions, abstentions, out-of-scope answers, and anything that
failed validation. A cached mistake is served to everyone.
"""

from __future__ import annotations

import base64
import json
import logging
import time
import uuid
from array import array
from math import sqrt
from typing import Any, Protocol

import redis

from ..config import Settings
from ..retrieval.base import RetrievalError
from ..retrieval.embedding import embed_query
from ..schemas import AskResponse

log = logging.getLogger("rahbar.cache")


class Cache(Protocol):
    enabled: bool

    def lookup(self, question: str, index_id: str) -> AskResponse | None: ...

    def store(self, question: str, index_id: str, response: AskResponse) -> None: ...

    def ping(self) -> None:
        """Raises when the cache backend cannot be reached."""
        ...


class NullCache:
    enabled = False

    def lookup(self, question: str, index_id: str) -> AskResponse | None:
        return None

    def store(self, question: str, index_id: str, response: AskResponse) -> None:
        return None

    def ping(self) -> None:
        return None


def _unit(vector: list[float]) -> list[float]:
    norm = sqrt(sum(x * x for x in vector)) or 1.0
    return [x / norm for x in vector]


def _encode(vector: list[float]) -> str:
    return base64.b64encode(array("f", vector).tobytes()).decode("ascii")


def _decode(text: str) -> list[float]:
    values = array("f")
    values.frombytes(base64.b64decode(text))
    return list(values)


class RedisCache:
    enabled = True

    def __init__(self, client: Any, settings: Settings) -> None:
        self.client = client
        self.settings = settings

    def _ids_key(self, index_id: str) -> str:
        return f"rahbar:cache:{index_id}:ids"

    def _entry_key(self, index_id: str, entry_id: str) -> str:
        return f"rahbar:cache:{index_id}:entry:{entry_id}"

    def ping(self) -> None:
        self.client.ping()

    def lookup(self, question: str, index_id: str) -> AskResponse | None:
        try:
            vector = _unit(embed_query(self.settings, question))
            ids_key = self._ids_key(index_id)
            ids = self.client.zrange(ids_key, 0, -1)
            if not ids:
                return None
            values = self.client.mget([self._entry_key(index_id, i) for i in ids])
            best: dict[str, Any] | None = None
            best_score = -1.0
            gone = []
            for entry_id, raw in zip(ids, values):
                if raw is None:
                    gone.append(entry_id)
                    continue
                entry = json.loads(raw)
                score = sum(a * b for a, b in zip(vector, _decode(entry["vector"])))
                if score > best_score:
                    best, best_score = entry, score
            if gone:
                self.client.zrem(ids_key, *gone)
        except (redis.RedisError, RetrievalError) as exc:
            log.warning("cache lookup skipped", extra={"error": type(exc).__name__})
            return None
        if best is None or best_score < self.settings.cache_threshold:
            return None
        log.info("cache hit", extra={"similarity": round(best_score, 4),
                                     "cached_question": best["question"]})
        return AskResponse.model_validate({**best["response"], "request_id": "", "cached": True})

    def store(self, question: str, index_id: str, response: AskResponse) -> None:
        try:
            vector = _unit(embed_query(self.settings, question))
            entry_id = uuid.uuid4().hex
            payload = json.dumps({
                "vector": _encode(vector), "question": question,
                "response": response.model_dump(mode="json", exclude={"request_id", "cached"}),
            })
            ids_key = self._ids_key(index_id)
            ttl = self.settings.cache_ttl_seconds
            self.client.set(self._entry_key(index_id, entry_id), payload, ex=ttl)
            self.client.zadd(ids_key, {entry_id: time.time()})
            self.client.expire(ids_key, ttl)
            excess = int(self.client.zcard(ids_key)) - self.settings.cache_max_entries
            if excess > 0:
                evicted = self.client.zpopmin(ids_key, excess)
                self.client.delete(*[self._entry_key(index_id, member) for member, _ in evicted])
        except (redis.RedisError, RetrievalError) as exc:
            log.warning("cache store skipped", extra={"error": type(exc).__name__})


def never_cache(response: AskResponse, *, fallback: bool, follow_up: bool) -> bool:
    """Follow-ups, abstentions, out-of-scope answers and failed validations are never cached."""
    return follow_up or fallback or not response.answered_from_context


def get_cache(settings: Settings) -> Cache:
    """The cache needs real embeddings and a Redis, so it stays off with the stub retriever."""
    if settings.retriever != "chroma" or not settings.redis_url:
        return NullCache()
    client = redis.Redis.from_url(settings.redis_url, decode_responses=True,
                                  socket_timeout=1.0, socket_connect_timeout=1.0)
    return RedisCache(client, settings)