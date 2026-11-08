"""Stage 5: Store. The only code in the whole system that writes to Chroma."""

from __future__ import annotations

import uuid
from typing import Any

from .config import IndexerSettings
from .models import Chunk

BATCH_SIZE = 500


def get_client(settings: IndexerSettings) -> Any:
    import chromadb  # the thin client, from chromadb-client in requirements.txt
    from chromadb.config import Settings as ChromaSettings

    return chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port,
                               settings=ChromaSettings(anonymized_telemetry=False))


def store(chunks: list[Chunk], vectors: list[list[float]], settings: IndexerSettings) -> int:
    """Write every chunk with its vector and metadata, and record the embedding model
    and vector dimension in the collection metadata (section 4.4). Return the count.

    The new index is built beside the live one under a temporary name, then swapped in
    by deleting the old collection and renaming the new one. The API keeps serving the
    old index while the slow work happens, and the gap is a moment, not minutes.
    `index_id` is new on every build; the API puts it into cache keys so that a re-index
    makes every old cache entry miss.
    """
    if not chunks or len(chunks) != len(vectors):
        raise ValueError(f"need one vector per chunk, got {len(chunks)} chunks "
                         f"and {len(vectors)} vectors")
    client = get_client(settings)
    building = f"{settings.collection}-building"
    _drop(client, building)
    collection = client.create_collection(
        name=building,
        metadata={"hnsw:space": "cosine", "embed_model": settings.embed_model,
                  "dimension": len(vectors[0]), "index_id": uuid.uuid4().hex,
                  "chunk_size": settings.chunk_size, "chunk_overlap": settings.chunk_overlap},
    )
    for start in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[start:start + BATCH_SIZE]
        collection.add(ids=[c.id for c in batch], documents=[c.text for c in batch],
                       embeddings=vectors[start:start + BATCH_SIZE],
                       metadatas=[c.metadata() for c in batch])
    count = int(collection.count())
    if count != len(chunks):
        raise RuntimeError(f"wrote {len(chunks)} chunks but the collection holds {count}")
    _drop(client, settings.collection)
    collection.modify(name=settings.collection)
    return count


def _drop(client: Any, name: str) -> None:
    try:
        client.delete_collection(name)
    except Exception:  # the collection did not exist
        pass