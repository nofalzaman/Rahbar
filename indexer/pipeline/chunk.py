"""Stage 3: Chunk. Structure-aware, with overlap."""

from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import groupby

from .models import Chunk, Document

FIRST_SECTION = "Preamble"

# A heading is a Markdown '#' line, a short numbered line without sentence punctuation
# ('5.4 Academic Warning'), or a short ALL-CAPS line ('CHAPTER 5').
_HEADING = re.compile(
    r"^(?:#{1,6}\s+(?P<md>\S.*)"
    r"|\d+(?:\.\d+){0,3}\.?\s+[A-Z][^.;:!?|]{2,80}"
    r"|[A-Z][A-Z0-9 &,/()\-]{4,80})$"
)
# A new paragraph starts at a clause number, a bullet, '(a)' or a table row.
_PARAGRAPH_START = re.compile(
    r"^(?:\d+(?:\.\d+)+\.?\s|\d+\.\s|[-•*]\s|\([A-Za-z0-9]{1,3}\)\s|\|)"
)
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


@dataclass
class _Paragraph:
    section: str
    page: int
    text: str


def chunk(doc: Document, size: int, overlap: int) -> list[Chunk]:
    """Split on sections, then paragraphs, then sentences, keeping each chunk under
    `size` words, with `overlap` words shared between neighbours. Sizes are counted in
    whitespace-separated words, not model tokens. Every chunk keeps the section heading
    it sits under, its page, doc_version and superseded, and starts with that heading so
    the embedding sees it too."""
    if size <= 0 or not 0 <= overlap < size:
        raise ValueError(f"need 0 <= overlap < size, got size={size} overlap={overlap}")
    limit = size - overlap  # a piece plus the overlap tail never exceeds `size`
    chunks: list[Chunk] = []
    for section, group in groupby(_paragraphs(doc), key=lambda p: p.section):
        paragraphs = list(group)
        # A whole short rule can look like a heading and have no following body.
        # Keep that rule instead of silently dropping it when the next heading starts.
        if any(p.text for p in paragraphs):
            paragraphs = [p for p in paragraphs if p.text]
        units = [piece for paragraph in paragraphs for piece in _split(paragraph, limit)]
        for page, body in _pack(units, size, overlap):
            chunks.append(Chunk(id=f"{doc.source}-{len(chunks):04d}",
                                text=f"{section}\n{body}", source=doc.source,
                                section=section, page=page, doc_version=doc.doc_version,
                                superseded=doc.superseded))
    return chunks


def _heading(line: str) -> str | None:
    match = _HEADING.match(line)
    if match is None:
        return None
    return match.group("md") or line


def _paragraphs(doc: Document) -> list[_Paragraph]:
    paragraphs: list[_Paragraph] = []
    section = FIRST_SECTION
    parts: list[str] = []
    start_page = 1
    for page in doc.pages:
        for raw in page.text.splitlines():
            line = raw.strip()
            heading = _heading(line) if line else None
            in_table = bool(parts) and parts[0].startswith("|")
            if parts and (not line or heading or in_table or _PARAGRAPH_START.match(line)):
                paragraphs.append(_Paragraph(section, start_page, " ".join(parts)))
                parts = []
            if heading:
                section = heading
                if re.match(r"^\d+\.\d+", heading):
                    paragraphs.append(_Paragraph(section, page.page, ""))
            elif line:
                if not parts:
                    start_page = page.page
                parts.append(line)
    if parts:
        paragraphs.append(_Paragraph(section, start_page, " ".join(parts)))
    return paragraphs


def _split(paragraph: _Paragraph, limit: int) -> list[_Paragraph]:
    """The paragraph itself when it fits, otherwise its sentences, hard-split by words."""
    if len(paragraph.text.split()) <= limit:
        return [paragraph]
    pieces: list[_Paragraph] = []
    for sentence in _SENTENCE_END.split(paragraph.text):
        words = sentence.split()
        for start in range(0, len(words), limit):
            pieces.append(_Paragraph(paragraph.section, paragraph.page,
                                     " ".join(words[start:start + limit])))
    return pieces


def _pack(units: list[_Paragraph], size: int, overlap: int) -> list[tuple[int, str]]:
    """Fill chunks up to `size` words; each new chunk starts with the last `overlap`
    words of the previous one. Returns (page of first unit, body) pairs."""
    packed: list[tuple[int, str]] = []
    current: list[str] = []
    words = 0
    page = 1
    for unit in units:
        count = len(unit.text.split())
        if current and words + count > size:
            body = "\n".join(current)
            packed.append((page, body))
            tail = body.split()[-overlap:] if overlap else []
            current = [" ".join(tail)] if tail else []
            words = len(tail)
            page = unit.page
        if not current:
            page = unit.page
        current.append(unit.text)
        words += count
    if current:
        packed.append((page, "\n".join(current)))
    return packed
