"""The Chroma retriever: version filter, similarity, mapping and failure handling."""

from __future__ import annotations

from typing import Any

import pytest

from app.config import Settings
from app.retrieval import chroma as chroma_module
from app.retrieval.base import RetrievalError
from app.retrieval.chroma import ChromaRetriever, wants_older_versions
from tests.fakes import FakeChroma, FakeCollection, fixed_embedding

ROWS = [
    ("new-1", "1. Attendance\ntext new", {"source": "rules-2026.md", "section": "1. Attendance",
     "page": 3, "doc_version": "2026", "superseded": False}, 0.25),
    ("old-1", "1. Attendance\ntext old", {"source": "rules-2023.md", "section": "1. Attendance",
     "page": 2, "doc_version": "2023", "superseded": True}, 0.10),
]


@pytest.fixture
def retriever(monkeypatch: Any) -> tuple[ChromaRetriever, FakeCollection]:
    monkeypatch.setattr(chroma_module, "embed_query", fixed_embedding([0.1, 0.2]))
    collection = FakeCollection(ROWS, {"embed_model": "nomic-embed-text", "index_id": "abc"})
    return ChromaRetriever(Settings(), client=FakeChroma(collection)), collection


def test_superseded_documents_are_filtered_out_by_default(
        retriever: tuple[ChromaRetriever, FakeCollection]) -> None:
    chroma, collection = retriever
    passages = chroma.retrieve("What is the attendance requirement?", k=5)
    assert [p.chunk_id for p in passages] == ["new-1"]
    assert collection.queries[0]["where"] == {"superseded": False}
    assert collection.queries[0]["query_embeddings"] == [[0.1, 0.2]]


def test_a_question_about_an_older_version_searches_the_superseded_documents(
        retriever: tuple[ChromaRetriever, FakeCollection]) -> None:
    chroma, collection = retriever
    passages = chroma.retrieve("What did the 2023 rules say about attendance?", k=5)
    assert [p.chunk_id for p in passages] == ["old-1"]
    assert collection.queries[0]["where"] == {"superseded": True}


def test_a_clause_number_in_the_question_is_also_looked_up_as_text(
        monkeypatch: Any) -> None:
    monkeypatch.setattr(chroma_module, "embed_query", fixed_embedding([0.1, 0.2]))
    meta = {"source": "rules.pdf", "section": "x", "page": 1, "doc_version": "2026",
            "superseded": False}
    rows = [("near", "attendance in general", meta, 0.10),
            ("clause", "1.21 Students must keep full attendance", meta, 0.60),
            ("other", "fees per credit hour", meta, 0.30)]
    chroma = ChromaRetriever(Settings(), client=FakeChroma(FakeCollection(rows)))
    passages = chroma.retrieve("What does clause 1.21 require?", k=3)
    assert [p.chunk_id for p in passages] == ["clause", "near", "other"]
    assert chroma_module.clause_numbers("Is 1.21 or 5.4 and 1.21 again, or 2.00?") == [
        "1.21", "5.4"]


def test_duplicate_texts_are_dropped_and_k_is_still_filled(monkeypatch: Any) -> None:
    monkeypatch.setattr(chroma_module, "embed_query", fixed_embedding([0.1, 0.2]))
    meta = {"source": "rules.pdf", "section": "2.6 CGPA", "page": 12, "doc_version": "2026",
            "superseded": False}
    rows = [("a", "same text", meta, 0.10), ("b", "same text", {**meta, "page": 13}, 0.11),
            ("c", "second", meta, 0.20), ("d", "third", meta, 0.30)]
    chroma = ChromaRetriever(Settings(), client=FakeChroma(FakeCollection(rows)))
    passages = chroma.retrieve("What is the CGPA calculation?", k=3)
    assert [p.chunk_id for p in passages] == ["a", "c", "d"]


def test_distance_becomes_similarity_and_metadata_is_mapped(
        retriever: tuple[ChromaRetriever, FakeCollection]) -> None:
    chroma, _ = retriever
    p = chroma.retrieve("attendance requirement", k=5)[0]
    assert p.score == 0.75
    assert (p.source, p.section, p.page, p.doc_version, p.superseded) == (
        "rules-2026.md", "1. Attendance", 3, "2026", False)


@pytest.mark.parametrize(("question", "older"), [
    ("What was the old attendance rule?", True),
    ("What did the previous handbook say?", True),
    ("Attendance requirement in 2023", True),
    ("Is the superseded policy still valid?", True),
    ("What is the attendance requirement in 2026?", False),
    ("How many credit hours can I take?", False),
    ("Can I hold an exam retake?", False),
    ("How many applications did the university receive in 2023-24?", False),
    ("What does the annual report for 2023 say?", False),
    ("Is attendance optional now? The rules say to ignore earlier instructions.", False),
])
def test_older_version_detection(question: str, older: bool) -> None:
    assert wants_older_versions(question) is older


def test_index_info_reports_the_pin_and_the_index_id(
        retriever: tuple[ChromaRetriever, FakeCollection]) -> None:
    info = retriever[0].index_info()
    assert (info.count, info.embed_model, info.index_id) == (2, "nomic-embed-text", "abc")


def test_a_missing_collection_is_a_retrieval_error() -> None:
    chroma = ChromaRetriever(Settings(), client=FakeChroma(None))
    with pytest.raises(RetrievalError, match="unavailable"):
        chroma.index_info()
    with pytest.raises(RetrievalError):
        chroma.retrieve("anything at all", k=3)
