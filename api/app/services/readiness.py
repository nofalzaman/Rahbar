"""Readiness (sections 4.3 and 4.4): can this pod take traffic right now?

Ready means Chroma answers, the collection exists and is not empty, the index was built
with the same embedding model this pod is configured with, and Redis answers. The first
failing check is named, so `kubectl logs` and the 503 body say what is wrong.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import redis

from ..config import Settings
from ..retrieval.base import RetrievalError, Retriever
from .cache import Cache


@dataclass(frozen=True)
class Readiness:
    ready: bool
    failed: str | None = None
    detail: str = ""
    checks: dict[str, str] = field(default_factory=dict)


def check_readiness(settings: Settings, retriever: Retriever, cache: Cache) -> Readiness:
    if settings.retriever != "chroma":
        return Readiness(ready=True, checks={"mode": "stub"})
    try:
        info = retriever.index_info()
    except RetrievalError as exc:
        return Readiness(False, "chroma", str(exc), {"chroma": "failed"})
    checks = {"chroma": "ok"}
    if info.count == 0:
        return Readiness(False, "collection",
                         f"collection {settings.collection!r} exists but is empty",
                         {**checks, "collection": "empty"})
    checks["collection"] = f"{info.count} chunks"
    if info.embed_model != settings.embed_model:
        detail = (f"embedding model mismatch: the index was built with {info.embed_model!r} "
                  f"but this pod has EMBED_MODEL={settings.embed_model!r}")
        return Readiness(False, "embedding_model", detail,
                         {**checks, "embedding_model": "mismatch"})
    checks["embedding_model"] = settings.embed_model
    try:
        cache.ping()
    except redis.RedisError as exc:
        return Readiness(False, "redis", f"redis is unreachable: {exc}",
                         {**checks, "redis": "failed"})
    checks["redis"] = "ok" if cache.enabled else "disabled"
    return Readiness(ready=True, checks=checks)