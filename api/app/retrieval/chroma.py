"""The real retriever: embed the question, ask Chroma for the closest chunks, and keep
superseded documents out unless the question is about an older version (section 3.2)."""

from __future__ import annotations

import re
from typing import Any

from ..config import Settings
from ..schemas import Passage
from .base import IndexInfo, RetrievalError
from .embedding import embed_query

# A question that names an older version, or a year before the current rules, may need
# the superseded documents. Anything else is answered from the current ones only.
_OLDER_VERSION = re.compile(
    r"\b(old|older|previous|previously|earlier|former|formerly|prior|superseded|repealed"
    r"|replaced|20(?:[01]\d|2[0-5]))\b",
    re.IGNORECASE,
)


def wants_older_versions(question: str) -> bool:
    return _OLDER_VERSION.search(question) is not None


class ChromaRetriever:
    name = "chroma"

    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        self.settings = settings
        self.client = client if client is not None else _http_client(settings)

    def _collection(self) -> Any:
        try:
            return self.client.get_collection(self.settings.collection)
        except Exception as exc:
            raise RetrievalError(
                f"collection {self.settings.collection!r} is unavailable: {exc}") from exc

    def index_info(self) -> IndexInfo:
        collection = self._collection()
        try:
            count = int(collection.count())
        except Exception as exc:
            raise RetrievalError(f"could not count the collection: {exc}") from exc
        metadata = collection.metadata or {}
        model = metadata.get("embed_model")
        return IndexInfo(count=count, embed_model=None if model is None else str(model),
                         index_id=str(metadata.get("index_id", "")))

    def retrieve(self, question: str, k: int) -> list[Passage]:
        collection = self._collection()
        vector = embed_query(self.settings, question)
        where = None if wants_older_versions(question) else {"superseded": False}
        try:
            result = collection.query(query_embeddings=[vector], n_results=k, where=where,
                                      include=["documents", "metadatas", "distances"])
        except Exception as exc:
            raise RetrievalError(f"vector search failed: {exc}") from exc
        passages = []
        for chunk_id, text, meta, distance in zip(result["ids"][0], result["documents"][0],
                                                  result["metadatas"][0],
                                                  result["distances"][0]):
            page = meta.get("page")
            passages.append(Passage(
                chunk_id=chunk_id, text=text, source=str(meta["source"]),
                section=str(meta["section"]), page=None if page is None else int(page),
                score=round(1 - float(distance), 4),
                doc_version=str(meta.get("doc_version", "")),
                superseded=bool(meta.get("superseded", False))))
        return passages


def _http_client(settings: Settings) -> Any:
    import chromadb  # the thin client, from chromadb-client in requirements.txt
    from chromadb.config import Settings as ChromaSettings

    return chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port,
                               settings=ChromaSettings(anonymized_telemetry=False))