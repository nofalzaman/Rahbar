"""Stage 2: Clean. Remove artefacts without destroying structure."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter

from .models import Document, Page

EDGE_LINES = 2           # a running header or footer sits in the first or last two lines
MIN_PAGES_FOR_REPEATS = 4
REPEAT_SHARE = 0.5       # an edge line seen on at least half of the pages is furniture


def clean(doc: Document) -> Document:
    """Strip headers and footers that repeat across pages and normalise whitespace.

    Headings, clause numbers, table rows and the document's own wording are kept,
    because chunking and citations depend on them.
    """
    repeated = _repeated_edge_lines(doc.pages)
    pages = [Page(source=page.source, page=page.page, ocr=page.ocr,
                  text=_normalise(_drop_repeated(page.text, repeated)))
             for page in doc.pages]
    return Document(source=doc.source, doc_version=doc.doc_version,
                    superseded=doc.superseded, pages=pages)


_PAGE_NUMBER = re.compile(r"(?:page\s*)?\d+(?:\s*(?:of|/)\s*\d+)?$")


def _signature(line: str) -> str:
    """A line without its trailing page number, so 'Handbook | Page 3 of 53' and
    'Handbook | Page 4 of 53' match, while '5.3 Scope' and '5.4 Scope' do not."""
    text = _PAGE_NUMBER.sub("", line.strip().lower().strip(" |-–")).strip(" |-–")
    return text or "<page number>"


def _is_candidate(line: str) -> bool:
    """Table rows are never page furniture, even when they repeat on every page."""
    return bool(line.strip()) and not line.lstrip().startswith("|")


def _edge_indexes(lines: list[str]) -> set[int]:
    filled = [index for index, line in enumerate(lines) if line.strip()]
    return set(filled[:EDGE_LINES] + filled[-EDGE_LINES:])


def _repeated_edge_lines(pages: list[Page]) -> set[str]:
    if len(pages) < MIN_PAGES_FOR_REPEATS:
        return set()
    seen: Counter[str] = Counter()
    for page in pages:
        lines = page.text.splitlines()
        seen.update({_signature(lines[i]) for i in _edge_indexes(lines)
                     if _is_candidate(lines[i])})
    threshold = len(pages) * REPEAT_SHARE
    return {signature for signature, count in seen.items() if count >= threshold}


def _drop_repeated(text: str, repeated: set[str]) -> str:
    lines = text.splitlines()
    edges = _edge_indexes(lines)
    kept = [line for index, line in enumerate(lines)
            if not (index in edges and _is_candidate(line) and _signature(line) in repeated)]
    return "\n".join(kept)


def _normalise(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).replace("\f", "")
    text = "\n".join(re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines())
    text = re.sub(r"(\w)-\n([a-z])", r"\1\2", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()