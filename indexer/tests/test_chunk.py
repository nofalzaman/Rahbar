"""Chunking: sections, paragraphs, sentences, overlap, stable ids and metadata."""

from __future__ import annotations

import pytest

from pipeline.chunk import chunk
from pipeline.models import Document, Page


def make_doc(text: str, source: str = "rules.pdf", superseded: bool = False) -> Document:
    return Document(source=source, doc_version="2026-06", superseded=superseded,
                    pages=[Page(source=source, page=1, text=text)])


def body_of(text: str) -> str:
    return text.split("\n", 1)[1]


def test_each_chunk_carries_its_section_and_all_five_metadata_fields() -> None:
    doc = make_doc("## 1. Attendance\n1.1 Attend 80 percent.\n## 2. Warning\n2.1 CGPA below 2.00.",
                   superseded=True)
    chunks = chunk(doc, 400, 50)
    assert [c.section for c in chunks] == ["1. Attendance", "2. Warning"]
    assert chunks[0].text.startswith("1. Attendance\n1.1 Attend 80 percent.")
    assert set(chunks[0].metadata()) == {"source", "section", "page", "doc_version", "superseded"}
    assert (chunks[0].source, chunks[0].doc_version, chunks[0].superseded) == (
        "rules.pdf", "2026-06", True)


def test_numbered_and_capitalised_lines_are_headings_but_clauses_are_not() -> None:
    doc = make_doc("CHAPTER FIVE\n5.4 Academic Warning\n"
                   "5.4.1 A student below 2.00 CGPA is placed on warning.\n"
                   "5.4.2 Warning lasts one semester.")
    chunks = chunk(doc, 400, 50)
    assert [c.section for c in chunks] == ["5.4 Academic Warning"]
    assert "5.4.1 A student below 2.00 CGPA" in chunks[0].text
    assert "5.4.2 Warning lasts one semester." in chunks[0].text


def test_chunks_never_span_two_sections() -> None:
    doc = make_doc("## A\n" + "alpha " * 30 + "\n## B\n" + "beta " * 30)
    for c in chunk(doc, 400, 50):
        assert ("beta" in c.text) != ("alpha" in c.text)


def test_chunks_stay_under_the_size_and_neighbours_share_the_overlap() -> None:
    words = " ".join(f"w{i}" for i in range(1000))
    chunks = chunk(make_doc("## Long\n" + words), 100, 20)
    assert len(chunks) > 5
    bodies = [body_of(c.text) for c in chunks]
    assert all(len(b.split()) <= 100 for b in bodies)
    for before, after in zip(bodies, bodies[1:]):
        assert after.split()[:20] == before.split()[-20:]


def test_every_word_is_stored_at_least_once() -> None:
    words = [f"w{i}" for i in range(500)]
    chunks = chunk(make_doc("## Long\n" + " ".join(words)), 100, 20)
    stored = {w for c in chunks for w in body_of(c.text).split()}
    assert stored == set(words)


def test_table_rows_keep_their_own_lines() -> None:
    doc = make_doc("## 1. Tuition\n| Programme | Fee |\n| --- | --- |\n| BS | 10,000 |\n"
                   "Fees are per credit hour.")
    text = chunk(doc, 400, 50)[0].text
    assert "| Programme | Fee |\n| --- | --- |\n| BS | 10,000 |\nFees are per credit hour." in text


def test_ids_are_stable_unique_and_start_with_the_source() -> None:
    doc = make_doc("## A\n" + "x " * 300 + "\n## B\nshort")
    first, second = chunk(doc, 100, 10), chunk(doc, 100, 10)
    ids = [c.id for c in first]
    assert ids == [c.id for c in second]
    assert len(set(ids)) == len(ids)
    assert all(i.startswith("rules.pdf-") for i in ids)


def test_a_chunk_reports_the_page_where_its_text_starts() -> None:
    doc = Document(source="r.pdf", doc_version="1", superseded=False, pages=[
        Page(source="r.pdf", page=1, text="## A\nFirst page clause."),
        Page(source="r.pdf", page=2, text="Second page continues here.")])
    assert chunk(doc, 400, 50)[0].page == 1


def test_a_very_long_sentence_is_split_by_words() -> None:
    chunks = chunk(make_doc("## S\n" + "word " * 500), 100, 10)
    assert all(len(body_of(c.text).split()) <= 100 for c in chunks)


def test_text_before_the_first_heading_goes_into_a_preamble_section() -> None:
    assert chunk(make_doc("Some opening text."), 400, 50)[0].section == "Preamble"


def test_an_empty_document_gives_no_chunks() -> None:
    assert chunk(make_doc(""), 400, 50) == []


def test_standalone_numbered_rules_are_not_lost_as_empty_headings() -> None:
    doc = make_doc("4.25 Deadline to withdraw is the last day of classes\n"
                   "4.26 Students on financial support cannot withdraw\n"
                   "## Next section\nOther text.")
    pieces = chunk(doc, 400, 50)
    assert any("last day of classes" in p.text for p in pieces)
    assert any("cannot withdraw" in p.text for p in pieces)


@pytest.mark.parametrize(("size", "overlap"), [(0, 0), (50, 50), (50, -1), (10, 20)])
def test_impossible_sizes_are_refused(size: int, overlap: int) -> None:
    with pytest.raises(ValueError, match="overlap"):
        chunk(make_doc("text"), size, overlap)
