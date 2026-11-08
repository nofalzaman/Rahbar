"""Hand-made stand-ins for Chroma, Redis, the retriever and the model. No network, ever."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import redis

from app.retrieval.base import IndexInfo, RetrievalError
from app.schemas import Answer, Citation, Passage


def passage(section: str = "1. Attendance", score: float = 0.8, **kw: Any) -> Passage:
    values: dict[str, Any] = {
        "chunk_id": f"doc-{section[:1]}", "text": f"{section}\nA student must attend 80 percent.",
        "source": "rules.md", "section": section, "page": 1, "score": score,
        "doc_version": "2026", "superseded": False}
    values.update(kw)
    return Passage(**values)


def good_answer(p: Passage | None = None, **kw: Any) -> Answer:
    p = p or passage()
    values: dict[str, Any] = {
        "reasoning": "r", "answer": "80 percent.", "answered_from_context": True,
        "citations": [Citation(source=p.source, section=p.section, page=p.page)],
        "confidence": "high"}
    values.update(kw)
    return Answer(**values)


class ScriptedProvider:
    """Returns or raises the next scripted item on every call."""

    name = "scripted"

    def __init__(self, *script: Answer | Exception) -> None:
        self.script = list(script)
        self.calls: list[tuple[str, list[Passage]]] = []

    def generate(self, question: str, passages: list[Passage]) -> Answer:
        self.calls.append((question, passages))
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeRetriever:
    name = "fake"

    def __init__(self, passages: list[Passage], info: IndexInfo | None = None) -> None:
        self.passages = passages
        self.info = info or IndexInfo(count=5, embed_model="nomic-embed-text", index_id="idx-1")
        self.retrieve_calls = 0
        self.error: RetrievalError | None = None

    def retrieve(self, question: str, k: int) -> list[Passage]:
        self.retrieve_calls += 1
        if self.error:
            raise self.error
        return self.passages[:k]

    def index_info(self) -> IndexInfo:
        if self.error:
            raise self.error
        return self.info


class FakeRedis:
    """The few Redis commands the cache uses, kept in dictionaries."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.zsets: dict[str, dict[str, float]] = {}
        self.ttls: dict[str, int] = {}
        self.down = False

    def _check(self) -> None:
        if self.down:
            raise redis.ConnectionError("redis is down")

    def ping(self) -> bool:
        self._check()
        return True

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._check()
        self.values[key] = value
        if ex is not None:
            self.ttls[key] = ex

    def mget(self, keys: list[str]) -> list[str | None]:
        self._check()
        return [self.values.get(k) for k in keys]

    def zadd(self, key: str, mapping: dict[str, float]) -> None:
        self._check()
        self.zsets.setdefault(key, {}).update(mapping)

    def zrange(self, key: str, start: int, end: int) -> list[str]:
        self._check()
        members = self.zsets.get(key, {})
        return sorted(members, key=lambda m: members[m])

    def zrem(self, key: str, *members: str) -> None:
        self._check()
        for member in members:
            self.zsets.get(key, {}).pop(member, None)

    def zcard(self, key: str) -> int:
        self._check()
        return len(self.zsets.get(key, {}))

    def zpopmin(self, key: str, count: int) -> list[tuple[str, float]]:
        self._check()
        popped = [(m, self.zsets[key][m]) for m in self.zrange(key, 0, -1)[:count]]
        for member, _ in popped:
            del self.zsets[key][member]
        return popped

    def expire(self, key: str, seconds: int) -> None:
        self._check()
        self.ttls[key] = seconds

    def delete(self, *keys: str) -> None:
        self._check()
        for key in keys:
            self.values.pop(key, None)


class FakeCollection:
    def __init__(self, rows: list[tuple[str, str, dict[str, Any], float]],
                 metadata: dict[str, Any] | None = None) -> None:
        self.rows = rows
        self.metadata = metadata
        self.queries: list[dict[str, Any]] = []

    def count(self) -> int:
        return len(self.rows)

    def query(self, **kw: Any) -> dict[str, Any]:
        self.queries.append(kw)
        where = kw.get("where")
        rows = [r for r in self.rows
                if not where or r[2].get("superseded") == where["superseded"]]
        rows = rows[: kw["n_results"]]
        return {"ids": [[r[0] for r in rows]], "documents": [[r[1] for r in rows]],
                "metadatas": [[r[2] for r in rows]], "distances": [[r[3] for r in rows]]}


class FakeChroma:
    def __init__(self, collection: FakeCollection | None = None) -> None:
        self.collection = collection

    def get_collection(self, name: str) -> FakeCollection:
        if self.collection is None:
            raise ValueError(f"Collection {name} does not exist")
        return self.collection


def fixed_embedding(vector: list[float]) -> Callable[..., list[float]]:
    return lambda settings, question: vector