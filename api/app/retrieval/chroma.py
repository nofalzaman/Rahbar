"""The real retriever: embed the question, ask Chroma for the closest chunks, and keep
superseded documents out unless the question is about an older version (section 3.2)."""

from __future__ import annotations

import re
from typing import Any

from ..config import Settings
from ..schemas import Passage
from .base import IndexInfo, RetrievalError
from .embedding import embed_query

# A question that names an older version, or a year before the current rules, is about the
# superseded documents. Anything else is answered from the current ones only.
_OLDER_VERSION = re.compile(
    r"\b(old|older|previous|previously|earlier|former|formerly|prior|superseded|repealed"
    r"|replaced|20(?:[01]\d|2[0-5]))\b",
    re.IGNORECASE,
)
# Embeddings blur exact terms, so a clause number such as 1.21 is also looked up as text.
_CLAUSE_NUMBER = re.compile(r"\b\d+(?:\.\d+)+\b")
EXACT_TERMS = 2          # at most this many clause numbers are looked up as text
EXACT_HITS = 2           # and at most this many chunks are taken for each
OVERFETCH = 2            # ask for k * OVERFETCH so that duplicates can be dropped


def wants_older_versions(question: str) -> bool:
    match = _OLDER_VERSION.search(question)
    if match is None:
        return False
    if not match.group().startswith("20"):
        return True
    # A dated report or application statistic is not a request for a repealed policy.
    return re.search(r"\b(rules?|polic(?:y|ies)|handbook|attendance|regulations?)\b",
                     question, re.IGNORECASE) is not None


def clause_numbers(question: str) -> list[str]:
    return list(dict.fromkeys(_CLAUSE_NUMBER.findall(question)))[:EXACT_TERMS]


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
        """The closest chunks, best first. Chunks that contain a clause number named in the
        question come first, then the nearest by meaning; duplicate texts are dropped."""
        collection = self._collection()
        vector = embed_query(self.settings, question)
        where = {"superseded": wants_older_versions(question)}
        exact: list[Passage] = []
        for term in clause_numbers(question):
            exact += self._query(collection, vector, EXACT_HITS, where,
                                 where_document={"$contains": term})
        nearest = self._query(collection, vector, k * OVERFETCH, where)
        unique: list[Passage] = []
        seen: set[str] = set()
        for passage in exact + nearest:
            if passage.text not in seen:
                seen.add(passage.text)
                unique.append(passage)
        return unique[:k]

    def _query(self, collection: Any, vector: list[float], n: int, where: dict[str, Any],
               where_document: dict[str, Any] | None = None) -> list[Passage]:
        try:
            result = collection.query(query_embeddings=[vector], n_results=n, where=where,
                                      where_document=where_document,
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
