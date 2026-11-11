"""Stage 1: Extract. PDF (or HTML, or Markdown) to text, page by page."""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from .models import Document, Page

MIN_TEXT_CHARS = 20  # a PDF page with less text than this is treated as an image-only scan
OCR_DPI = 200

_SKIP_TAGS = {"script", "style", "nav", "header", "footer", "noscript", "svg"}
_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_BLOCK_TAGS = {"p", "div", "br", "li", "ul", "ol", "section", "article", "table"}


def extract(path: str, doc_version: str, superseded: bool) -> Document:
    """Return the document's text page by page.

    PDF pages with no text layer are OCR'd and marked ocr=True. Tables found by
    pdfplumber are written as Markdown rows. HTML headings become Markdown headings and
    HTML table rows become Markdown rows. Markdown and text files are one page.
    """
    file = Path(path)
    suffix = file.suffix.lower()
    if suffix == ".pdf":
        pages = _pdf_pages(file)
    elif suffix in {".html", ".htm"}:
        html = file.read_text(encoding="utf-8", errors="replace")
        pages = [Page(source=file.name, page=1, text=_html_to_text(html))]
    elif suffix in {".md", ".txt"}:
        text = _strip_front_matter(file.read_text(encoding="utf-8"))
        pages = [Page(source=file.name, page=1, text=text)]
    else:
        raise ValueError(f"unsupported document type: {file.name}")
    return Document(source=file.name, doc_version=doc_version, superseded=superseded,
                    pages=pages)


def _pdf_pages(path: Path) -> list[Page]:
    import pdfplumber

    pages: list[Page] = []
    with pdfplumber.open(path) as pdf:
        for number, pdf_page in enumerate(pdf.pages, start=1):
            text = _page_text(pdf_page)
            ocr = len(text.strip()) < MIN_TEXT_CHARS
            if ocr:
                text = _ocr_page(path, number)
            pages.append(Page(source=path.name, page=number, text=text, ocr=ocr))
            pdf_page.flush_cache()
    return pages


def _page_text(page: Any) -> str:
    """Text of one page, with each detected table rewritten as Markdown rows."""
    tables = page.find_tables()
    if not tables:
        return str(page.extract_text() or "")
    boxes = [table.bbox for table in tables]
    outside = page.filter(lambda obj: not _inside_any(obj, boxes))
    parts = [str(outside.extract_text() or "")]
    parts.extend(_table_to_markdown(table.extract()) for table in tables)
    return "\n".join(part for part in parts if part)


def _inside_any(obj: dict[str, Any], boxes: list[tuple[float, float, float, float]]) -> bool:
    if obj.get("object_type") != "char":
        return False
    x = (obj["x0"] + obj["x1"]) / 2
    y = (obj["top"] + obj["bottom"]) / 2
    return any(x0 <= x <= x1 and top <= y <= bottom for x0, top, x1, bottom in boxes)


def _table_to_markdown(rows: list[list[str | None]]) -> str:
    cleaned = [[" ".join((cell or "").split()) for cell in row] for row in rows]
    cleaned = [row for row in cleaned if any(row)]
    if not cleaned:
        return ""
    lines = ["| " + " | ".join(row) + " |" for row in cleaned]
    lines.insert(1, "| " + " | ".join("---" for _ in cleaned[0]) + " |")
    return "\n".join(lines)


def _ocr_page(path: Path, number: int) -> str:
    import pytesseract
    from pdf2image import convert_from_path

    images = convert_from_path(str(path), dpi=OCR_DPI, first_page=number, last_page=number)
    return "\n".join(str(pytesseract.image_to_string(image)) for image in images)


def _strip_front_matter(text: str) -> str:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return text
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return "\n".join(lines[index + 1:])
    return text


def _html_to_text(html: str) -> str:
    parser = _HtmlText()
    parser.feed(html)
    parser.close()
    return parser.text()


class _HtmlText(HTMLParser):
    """Visible text of a page: headings as '#' lines, table rows as '| a | b |' lines."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._lines: list[str] = []
        self._buffer: list[str] = []
        self._skip = 0
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._level = 0

    def text(self) -> str:
        self._flush()
        return "\n".join(self._lines)

    def _flush(self) -> None:
        text = " ".join("".join(self._buffer).split())
        self._buffer.clear()
        if text:
            self._lines.append(text)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip += 1
        elif self._skip:
            return
        elif tag == "tr":
            self._flush()
            self._row = []
        elif tag in {"td", "th"}:
            self._cell = []
        elif tag in _HEADING_TAGS:
            self._flush()
            self._level = int(tag[1])
        elif tag in _BLOCK_TAGS:
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            self._skip = max(0, self._skip - 1)
        elif self._skip:
            return
        elif tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if any(self._row):
                self._lines.append("| " + " | ".join(self._row) + " |")
            self._row = None
        elif tag in _HEADING_TAGS and self._level:
            text = " ".join("".join(self._buffer).split())
            self._buffer.clear()
            if text:
                self._lines.append("#" * self._level + " " + text)
            self._level = 0
        elif tag in _BLOCK_TAGS:
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        if self._cell is not None:
            self._cell.append(data)
        else:
            self._buffer.append(data)