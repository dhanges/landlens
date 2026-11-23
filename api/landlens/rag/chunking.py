"""PDF parsing and chunking (spec 2.13).

- PyMuPDF, page by page, text blocks in reading order. A page with under 50 characters of text is flagged as
  having no text layer (scanned); OCR is not run (OQ-36 stays open for those pages).
- Chunks of about 400 tokens with 15% overlap, built from words that remember their page, so every chunk has
  page_start / page_end. A chunk is cut early at a detected heading (CHAPTER / PART / SCHEDULE, numbered
  sections such as "12." or "12A.", FAQ questions "Q3.", short all-caps lines) once it holds >= 120 tokens;
  no overlap is carried across a heading cut, so a new section starts clean.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .llm import est_tokens

MIN_PAGE_CHARS = 50
TARGET_TOKENS = 400
OVERLAP = 0.15
MIN_TOKENS_BEFORE_HEADING = 120

HEADING = re.compile(
    r"^(?:(?:CHAPTER|PART|SCHEDULE)\b|\d{1,3}[A-Z]?\.\s*(?:\(\d+\)\s*)?[A-Z\"“(]|Q\d{1,3}\.)")


@dataclass
class Page:
    number: int                 # 1-based
    blocks: list[str]
    chars: int


@dataclass
class Parsed:
    path: Path
    title: str | None
    pages: list[Page]
    flagged: list[int] = field(default_factory=list)   # pages without a text layer

    @property
    def page_count(self) -> int:
        return len(self.pages)


@dataclass
class Chunk:
    chunk_no: int
    page_start: int
    page_end: int
    content: str

    @property
    def tokens(self) -> int:
        return est_tokens(self.content)


def _clean(text: str) -> str:
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)          # words hyphenated across lines
    return re.sub(r"\s+", " ", text).strip()


def is_heading(block: str) -> bool:
    first = block.strip().split("\n", 1)[0].strip()
    if HEADING.match(first):
        return True
    letters = [c for c in first if c.isalpha()]
    return 3 <= len(letters) and len(first) <= 80 and first.upper() == first and sum(c.isupper() for c in letters) == len(letters)


def parse(path: Path) -> Parsed:
    import pymupdf

    pages: list[Page] = []
    with pymupdf.open(path) as doc:
        title = (doc.metadata or {}).get("title") or None
        for i, page in enumerate(doc, start=1):
            blocks = [b[4] for b in page.get_text("blocks", sort=True) if b[6] == 0 and b[4].strip()]
            chars = sum(len(b.strip()) for b in blocks)
            pages.append(Page(i, blocks, chars))
    flagged = [p.number for p in pages if p.chars < MIN_PAGE_CHARS]
    return Parsed(path, title, pages, flagged)


def chunk(parsed: Parsed) -> list[Chunk]:
    # words as (text, page, starts_heading)
    words: list[tuple[str, int, bool]] = []
    for p in parsed.pages:
        if p.number in parsed.flagged:
            continue
        for b in p.blocks:
            ws = _clean(b).split(" ")
            ws = [w for w in ws if w]
            if not ws:
                continue
            head = is_heading(b)
            words += [(w, p.number, head and j == 0) for j, w in enumerate(ws)]

    chunks: list[Chunk] = []
    i, n = 0, len(words)
    while i < n:
        j, chars, cut_at_heading = i, 0, False
        while j < n:
            if j > i and words[j][2] and est_tokens("x" * chars) >= MIN_TOKENS_BEFORE_HEADING:
                cut_at_heading = True
                break
            chars += len(words[j][0]) + 1
            j += 1
            if est_tokens("x" * chars) >= TARGET_TOKENS:
                break
        piece = words[i:j]
        text = ""
        for k, (w, _, head) in enumerate(piece):
            text += ("\n\n" if head and k else (" " if k else "")) + w
        chunks.append(Chunk(len(chunks) + 1, piece[0][1], piece[-1][1], text))
        if j >= n:
            break
        back = 0 if cut_at_heading else max(1, int(len(piece) * OVERLAP))
        i = max(j - back, i + 1)
    return chunks
