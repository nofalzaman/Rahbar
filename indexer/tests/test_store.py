"""Storing: build beside the live index, swap, and record the pin. A fake client, no Chroma."""

from __future__ import annotations

from typing import Any

import pytest

from pipeline import store as store_module
from pipeline.config import get_settings
from pipeline.models import Chunk
from pipeline.store import store


class FakeCollection:
    def __init__(self, client: FakeClient, name: str, metadata: dict[str, Any]) -> None:
        self.client, self.name, self.metadata = client, name, metadata
        self.rows: dict[str, tuple[str, list[float], dict[str, Any]]] = {}

    def add(self, ids: list[str], documents: list[str], embeddings: list[list[float]],
            metadatas: list[dict[str, Any]]) -> None:
        for i, d, e, m in zip(ids, documents, embeddings, metadatas):
            self.rows[i] = (d, e, m)

    def count(self) -> int:
        return len(self.rows)

    def modify(self, name: str) -> None:
        del self.client.collections[self.name]
        self.name = name
        self.client.collections[name] = self


class FakeClient:
    def __init__(self) -> None:
        self.collections: dict[str, FakeCollection] = {}

    def delete_collection(self, name: str) -> None:
        if name not in self.collections:
            raise ValueError("no such collection")
        del self.collections[name]

    def create_collection(self, name: str, metadata: dict[str, Any]) -> FakeCollection:
        self.collections[name] = FakeCollection(self, name, metadata)
        return self.collections[name]


def make_chunks(count: int) -> list[Chunk]:
    return [Chunk(id=f"doc-{i:04d}", text=f"text {i}", source="doc.md", section="1. A", page=1,
                  doc_version="2026", superseded=False) for i in range(count)]


@pytest.fixture
def client(monkeypatch: Any) -> FakeClient:
    fake = FakeClient()
    monkeypatch.setattr(store_module, "get_client", lambda settings: fake)
    return fake


def test_the_index_is_written_and_the_pin_is_recorded(client: FakeClient) -> None:
    settings = get_settings()
    assert store(make_chunks(3), [[0.1, 0.2]] * 3, settings) == 3
    assert list(client.collections) == [settings.collection]
    collection = client.collections[settings.collection]
    assert collection.metadata["embed_model"] == settings.embed_model
    assert collection.metadata["dimension"] == 2
    assert collection.metadata["hnsw:space"] == "cosine"
    assert len(str(collection.metadata["index_id"])) == 32
    document, vector, metadata = collection.rows["doc-0001"]
    assert (document, vector) == ("text 1", [0.1, 0.2])
    assert set(metadata) == {"source", "section", "page", "doc_version", "superseded"}


def test_the_old_index_is_replaced_and_gets_a_new_index_id(client: FakeClient) -> None:
    settings = get_settings()
    store(make_chunks(2), [[1.0]] * 2, settings)
    first_id = client.collections[settings.collection].metadata["index_id"]
    store(make_chunks(5), [[1.0]] * 5, settings)
    collection = client.collections[settings.collection]
    assert collection.count() == 5
    assert collection.metadata["index_id"] != first_id
    assert list(client.collections) == [settings.collection]


def test_a_leftover_building_collection_from_a_failed_run_is_discarded(
        client: FakeClient) -> None:
    settings = get_settings()
    stale = client.create_collection(f"{settings.collection}-building", {})
    stale.add(["old"], ["old"], [[9.0]], [{}])
    store(make_chunks(1), [[1.0]], settings)
    assert client.collections[settings.collection].count() == 1


def test_large_indexes_are_written_in_batches(client: FakeClient, monkeypatch: Any) -> None:
    monkeypatch.setattr(store_module, "BATCH_SIZE", 2)
    assert store(make_chunks(5), [[1.0]] * 5, get_settings()) == 5


def test_chunks_and_vectors_must_match(client: FakeClient) -> None:
    with pytest.raises(ValueError, match="one vector per chunk"):
        store(make_chunks(2), [[1.0]], get_settings())


def test_an_empty_index_is_refused(client: FakeClient) -> None:
    with pytest.raises(ValueError, match="one vector per chunk"):
        store([], [], get_settings())