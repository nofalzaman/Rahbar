"""Embedding the question: the task prefix, the pinned model, memoising, failure."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from app.config import Settings
from app.retrieval import embedding
from app.retrieval.base import RetrievalError


def install(monkeypatch: Any, handler: Any) -> None:
    def post(url: str, **kw: Any) -> httpx.Response:
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            return client.post(url, **{k: v for k, v in kw.items() if k != "timeout"})

    monkeypatch.setattr(embedding.httpx, "post", post)
    embedding._embed.cache_clear()


def test_the_question_is_embedded_with_the_pinned_model_and_prefix(monkeypatch: Any) -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"embeddings": [[0.5, 0.25]]})

    install(monkeypatch, handler)
    settings = Settings(embed_model="nomic-embed-text", embed_query_prefix="search_query: ")
    assert embedding.embed_query(settings, "attendance?") == [0.5, 0.25]
    assert seen == [{"model": "nomic-embed-text", "input": "search_query: attendance?"}]


def test_the_same_question_is_embedded_once(monkeypatch: Any) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"embeddings": [[1.0]]})

    install(monkeypatch, handler)
    for _ in range(3):
        embedding.embed_query(Settings(), "same question")
    assert calls["n"] == 1


def test_a_failing_model_becomes_a_retrieval_error(monkeypatch: Any) -> None:
    install(monkeypatch, lambda request: httpx.Response(404, json={"error": "no such model"}))
    with pytest.raises(RetrievalError, match="could not embed"):
        embedding.embed_query(Settings(), "anything at all")