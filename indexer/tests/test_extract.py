"""Extraction: Markdown, HTML, PDF text, OCR fallback and tables. No network, no OCR engine."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from pipeline import extract as extract_module
from pipeline.extract import extract


def make_pdf(pages: list[str]) -> bytes:
    """A minimal valid PDF: one Helvetica text page per string ('' gives an empty page)."""
    count = len(pages)
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(count))
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>",
               f"<< /Type /Pages /Kids [{kids}] /Count {count} >>".encode(),
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    for i, text in enumerate(pages):
        objects.append((f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                        f"/Contents {5 + 2 * i} 0 R "
                        f"/Resources << /Font << /F1 3 0 R >> >> >>").encode())
        shown = b"".join(b"(" + line.replace("(", "\\(").replace(")", "\\)").encode() + b") Tj T* "
                         for line in text.splitlines())
        stream = b"BT /F1 12 Tf 72 720 Td 14 TL " + shown + b"ET" if text else b""
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref}\n%%EOF\n").encode()
    return bytes(out)


def test_markdown_front_matter_is_not_part_of_the_text(tmp_path: Path) -> None:
    path = tmp_path / "rules.md"
    path.write_text("---\ndoc_version: 2026\n---\n# Rules\n\nBody text.", encoding="utf-8")
    doc = extract(str(path), "2026", False)
    assert doc.source == "rules.md"
    assert (doc.doc_version, doc.superseded) == ("2026", False)
    assert doc.pages[0].text == "# Rules\n\nBody text."


def test_html_keeps_headings_and_table_rows_and_drops_boilerplate(tmp_path: Path) -> None:
    path = tmp_path / "fees.html"
    path.write_text(
        "<html><head><style>p{}</style></head><body><nav>Home About</nav>"
        "<h2>Tuition</h2><p>Fees per credit hour.</p>"
        "<table><tr><th>Programme</th><th>Fee</th></tr>"
        "<tr><td>BS</td><td>10,000</td></tr></table>"
        "<footer>Copyright</footer></body></html>", encoding="utf-8")
    text = extract(str(path), "2026-27", False).pages[0].text
    assert text.splitlines() == ["## Tuition", "Fees per credit hour.",
                                 "| Programme | Fee |", "| BS | 10,000 |"]


def test_pdf_text_is_extracted_page_by_page(tmp_path: Path) -> None:
    path = tmp_path / "rules.pdf"
    path.write_bytes(make_pdf(["5.4 Academic Warning\nCGPA below 2.00.", "Second page text here."]))
    doc = extract(str(path), "2026-06", False)
    assert [page.page for page in doc.pages] == [1, 2]
    assert "CGPA below 2.00." in doc.pages[0].text
    assert "Second page text here." in doc.pages[1].text
    assert not any(page.ocr for page in doc.pages)


def test_a_page_without_a_text_layer_is_ocred(tmp_path: Path, monkeypatch: Any) -> None:
    path = tmp_path / "scan.pdf"
    path.write_bytes(make_pdf(["", "This page has a real text layer of its own."]))
    monkeypatch.setattr(extract_module, "_ocr_page",
                        lambda pdf, number: f"ocr text of page {number}")
    doc = extract(str(path), "2022-05", False)
    assert (doc.pages[0].ocr, doc.pages[0].text) == (True, "ocr text of page 1")
    assert doc.pages[1].ocr is False


def test_table_rows_become_markdown_with_a_separator() -> None:
    rows = [["Charge", "Amount"], [None, None], ["Late  fee", "3,000"]]
    assert extract_module._table_to_markdown(rows).splitlines() == [
        "| Charge | Amount |", "| --- | --- |", "| Late fee | 3,000 |"]


def test_text_inside_a_table_is_not_extracted_twice() -> None:
    class Table:
        bbox = (0.0, 0.0, 10.0, 10.0)

        def extract(self) -> list[list[str | None]]:
            return [["A", "B"], ["1", "2"]]

    class Outside:
        def extract_text(self) -> str:
            return "Text outside the table."

    class Page:
        def find_tables(self) -> list[Table]:
            return [Table()]

        def filter(self, keep: Any) -> Outside:
            inside = {"object_type": "char", "x0": 1, "x1": 3, "top": 1, "bottom": 3}
            beyond = {"object_type": "char", "x0": 50, "x1": 53, "top": 50, "bottom": 53}
            assert (keep(inside), keep(beyond)) == (False, True)
            return Outside()

    text = extract_module._page_text(Page())
    assert text.splitlines() == ["Text outside the table.", "| A | B |", "| --- | --- |",
                                 "| 1 | 2 |"]


def test_an_unsupported_file_type_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "slides.pptx"
    path.write_bytes(b"x")
    with pytest.raises(ValueError, match="unsupported"):
        extract(str(path), "x", False)