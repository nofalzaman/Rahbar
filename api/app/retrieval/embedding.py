"""Embed a question with the pinned model, exactly as the indexer embedded the chunks."""

from __future__ import annotations

from functools import lru_cache

import httpx

from ..config import Settings
from .base import RetrievalError

TIMEOUT_SECONDS = 10.0


@lru_cache(maxsize=256)
def _embed(ollama_url: str, model: str, text: str) -> tuple[float, ...]:
    response = httpx.post(f"{ollama_url}/api/embed", json={"model": model, "input": text},
                          timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    return tuple(response.json()["embeddings"][0])


def embed_query(settings: Settings, question: str) -> list[float]:
    """The cache and the retriever both need the vector, so repeated questions are
    served from a small in-process memo instead of calling the model twice."""
    try:
        return list(_embed(settings.ollama_url, settings.embed_model,
                           settings.embed_query_prefix + question))
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
        raise RetrievalError(
            f"could not embed the question with {settings.embed_model}: {exc}") from exc