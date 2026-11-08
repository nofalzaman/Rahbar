"""Embedding: batching, the pinned model name, retries and count checks. No Ollama needed."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from pipeline import embed as embed_module
from pipeline.config import get_settings
from pipeline.embed import embed

RealClient = httpx.Client


def install(monkeypatch: Any, handler: Any) -> None:
    monkeypatch.setattr(embed_module.httpx, "Client",
                        lambda **kw: RealClient(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setattr(embed_module.time, "sleep", lambda _s: None)


def test_texts_are_embedded_in_batches_with_the_pinned_model(monkeypatch: Any) -> None:
    requests: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        return httpx.Response(200, json={"embeddings": [[float(len(t))] for t in body["input"]]})

    install(monkeypatch, handler)
    monkeypatch.setattr(embed_module, "BATCH_SIZE", 2)
    vectors = embed(["a", "bb", "ccc", "dddd", "e"], get_settings())
    assert vectors == [[1.0], [2.0], [3.0], [4.0], [1.0]]
    assert [len(r["input"]) for r in requests] == [2, 2, 1]
    assert {r["model"] for r in requests} == {get_settings().embed_model}


def test_a_failed_request_is_retried(monkeypatch: Any) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(500)
        return httpx.Response(200, json={"embeddings": [[0.5]]})

    install(monkeypatch, handler)
    assert embed(["text"], get_settings()) == [[0.5]]
    assert calls["n"] == 2


def test_the_job_fails_when_the_model_never_answers(monkeypatch: Any) -> None:
    install(monkeypatch, lambda request: httpx.Response(404, json={"error": "model not found"}))
    with pytest.raises(RuntimeError, match="failed after"):
        embed(["text"], get_settings())


def test_a_wrong_number_of_vectors_is_an_error(monkeypatch: Any) -> None:
    install(monkeypatch, lambda request: httpx.Response(200, json={"embeddings": [[1.0]]}))
    with pytest.raises(RuntimeError, match="asked for 2"):
        embed(["a", "b"], get_settings())


def test_no_texts_means_no_requests(monkeypatch: Any) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request expected")

    install(monkeypatch, handler)
    assert embed([], get_settings()) == []