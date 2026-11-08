"""/readyz names the failed dependency, /healthz needs none, and /api/ask maps errors."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.retrieval.base import IndexInfo, RetrievalError
from app.services.cache import RedisCache
from tests.fakes import FakeRedis, FakeRetriever, ScriptedProvider, good_answer, passage


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("RETRIEVER", "stub")
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    from app.main import app

    with TestClient(app) as c:
        yield c


def go_live(client: TestClient, info: IndexInfo | None = None) -> tuple[FakeRetriever, FakeRedis]:
    """Switch the running app to the chroma path with fakes behind it."""
    state = client.app.state                                    # type: ignore[attr-defined]
    settings = replace(Settings(), retriever="chroma", embed_model="nomic-embed-text",
                       redis_url="redis://r:6379/0")
    retriever = FakeRetriever([passage()], info)
    redis_client = FakeRedis()
    state.settings, state.retriever = settings, retriever
    state.cache = RedisCache(redis_client, settings)
    state.last_readiness = None
    return retriever, redis_client


def test_ready_when_everything_is_healthy(client: TestClient) -> None:
    go_live(client)
    body = client.get("/readyz").json()
    assert (client.get("/readyz").status_code, body["status"]) == (200, "ready")
    assert body["checks"]["embedding_model"] == "nomic-embed-text"


def test_stub_mode_is_ready_without_any_dependency(client: TestClient) -> None:
    assert client.get("/readyz").json() == {"status": "ready", "checks": {"mode": "stub"}}


def test_unreachable_chroma_is_503_and_named(client: TestClient) -> None:
    retriever, _ = go_live(client)
    retriever.error = RetrievalError("connection refused")
    r = client.get("/readyz")
    assert (r.status_code, r.json()["failed"]) == (503, "chroma")


def test_an_empty_collection_is_503(client: TestClient) -> None:
    go_live(client, IndexInfo(count=0, embed_model="nomic-embed-text", index_id="i"))
    r = client.get("/readyz")
    assert (r.status_code, r.json()["failed"]) == (503, "collection")


def test_an_embedding_model_mismatch_is_503_and_names_both_models(
        client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    go_live(client, IndexInfo(count=100, embed_model="all-minilm", index_id="i"))
    with caplog.at_level("ERROR"):
        r = client.get("/readyz")
    body = r.json()
    assert (r.status_code, body["failed"]) == (503, "embedding_model")
    assert "'all-minilm'" in body["detail"] and "'nomic-embed-text'" in body["detail"]
    assert any("not ready" in rec.getMessage() for rec in caplog.records)


def test_unreachable_redis_is_503(client: TestClient) -> None:
    _, redis_client = go_live(client)
    redis_client.down = True
    r = client.get("/readyz")
    assert (r.status_code, r.json()["failed"]) == (503, "redis")


def test_liveness_never_touches_a_dependency(client: TestClient) -> None:
    retriever, redis_client = go_live(client)
    retriever.error = RetrievalError("everything is on fire")
    redis_client.down = True
    assert client.get("/healthz").status_code == 200


def test_a_retrieval_failure_is_a_503_with_a_plain_message_not_a_500(
        client: TestClient) -> None:
    retriever, _ = go_live(client)
    retriever.error = RetrievalError("chroma is down")
    r = client.post("/api/ask", json={"question": "What is the attendance rule?"})
    assert r.status_code == 503
    assert "unavailable" in r.json()["detail"]


def test_the_cache_header_and_the_follow_up_flag_reach_the_pipeline(
        client: TestClient, monkeypatch: Any) -> None:
    from app.services import cache as cache_module

    monkeypatch.setattr(cache_module, "embed_query", lambda settings, q: [1.0, 0.0])
    retriever, _ = go_live(client)
    state = client.app.state                                    # type: ignore[attr-defined]
    state.provider = ScriptedProvider(good_answer(), good_answer())
    miss = client.post("/api/ask", json={"question": "attendance?"})
    hit = client.post("/api/ask", json={"question": "attendance?"})
    follow = client.post("/api/ask", json={"question": "attendance?", "follow_up": True})
    assert (miss.headers["X-Cache"], hit.headers["X-Cache"]) == ("miss", "hit")
    assert follow.headers["X-Cache"] == "miss" and follow.json()["cached"] is False
    assert retriever.retrieve_calls == 2


def test_new_pipeline_metrics_are_exposed(client: TestClient) -> None:
    client.post("/api/ask", json={"question": "Count the stub request"})
    text = client.get("/metrics").text
    for name in ("rahbar_retrieval_seconds", "rahbar_generation_seconds",
                 "rahbar_cache_lookups_total", "rahbar_abstentions_total",
                 "rahbar_fallbacks_total", "rahbar_tokens_total"):
        assert name in text