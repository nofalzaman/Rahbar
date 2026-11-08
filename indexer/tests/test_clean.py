"""Cleaning: repeated headers and footers go; headings, clauses and table rows stay."""

from __future__ import annotations

from pipeline.clean import clean
from pipeline.models import Document, Page


def make_doc(texts: list[str]) -> Document:
    pages = [Page(source="rules.pdf", page=i, text=t) for i, t in enumerate(texts, start=1)]
    return Document(source="rules.pdf", doc_version="2026", superseded=False, pages=pages)


def numbered_pages(count: int) -> Document:
    return make_doc([
        f"FAST-NUCES Academic Rules Handbook\n5.{i} Heading {i}\nClause body {i}.\n"
        f"| Charge | Amount |\nPage {i} of {count}" for i in range(1, count + 1)])


def test_running_headers_and_page_numbers_are_removed() -> None:
    cleaned = clean(numbered_pages(6))
    for page in cleaned.pages:
        assert "FAST-NUCES" not in page.text
        assert "Page " not in page.text


def test_headings_clauses_and_table_rows_survive() -> None:
    cleaned = clean(numbered_pages(6))
    text = cleaned.pages[2].text
    assert "5.3 Heading 3" in text
    assert "Clause body 3." in text
    assert "| Charge | Amount |" in text


def test_a_short_document_is_left_alone() -> None:
    doc = numbered_pages(3)
    assert "FAST-NUCES" in clean(doc).pages[0].text


def test_a_line_repeated_in_the_body_is_not_treated_as_furniture() -> None:
    texts = [f"Intro line {i}\nOne\nNote: see above\nTwo\nThree\nEnd line {i}" for i in range(6)]
    assert all("Note: see above" in page.text for page in clean(make_doc(texts)).pages)


def test_hyphenated_line_breaks_are_joined_and_whitespace_is_collapsed() -> None:
    cleaned = clean(make_doc(["The informa-\ntion   office\xa0is  open.\n\n\n\nNext."]))
    assert cleaned.pages[0].text == "The information office is open.\n\nNext."


def test_ligatures_are_normalised() -> None:
    assert clean(make_doc(["o\ufb03ce \ufb01le"])).pages[0].text == "office file"


def test_page_metadata_is_preserved() -> None:
    doc = Document(source="scan.pdf", doc_version="2022-05", superseded=True,
                   pages=[Page(source="scan.pdf", page=7, text="Text.", ocr=True)])
    cleaned = clean(doc)
    assert (cleaned.source, cleaned.doc_version, cleaned.superseded) == (
        "scan.pdf", "2022-05", True)
    assert (cleaned.pages[0].page, cleaned.pages[0].ocr) == (7, True)