"""Stage 4: Embed. One vector per chunk, from the pinned model only."""

from __future__ import annotations

import time

import httpx

from .config import IndexerSettings

BATCH_SIZE = 16
TIMEOUT_SECONDS = 300.0
ATTEMPTS = 3


def embed(texts: list[str], settings: IndexerSettings) -> list[list[float]]:
    """Embed with settings.embed_model and nothing else, in batches, through Ollama:
    POST {ollama_url}/api/embed returns one vector per input text."""
    vectors: list[list[float]] = []
    with httpx.Client(base_url=settings.ollama_url, timeout=TIMEOUT_SECONDS) as client:
        for start in range(0, len(texts), BATCH_SIZE):
            vectors.extend(_embed_batch(client, texts[start:start + BATCH_SIZE],
                                        settings.embed_model))
    return vectors


def _embed_batch(client: httpx.Client, batch: list[str], model: str) -> list[list[float]]:
    last_error: Exception | None = None
    for attempt in range(ATTEMPTS):
        try:
            response = client.post("/api/embed", json={"model": model, "input": batch})
            response.raise_for_status()
            embeddings: list[list[float]] = response.json()["embeddings"]
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            last_error = exc
            if attempt < ATTEMPTS - 1:
                time.sleep(2 * (attempt + 1))
            continue
        if len(embeddings) != len(batch):
            raise RuntimeError(f"asked for {len(batch)} embeddings, got {len(embeddings)}")
        return embeddings
    raise RuntimeError(f"embedding with {model} failed after {ATTEMPTS} attempts") from last_error