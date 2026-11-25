"""Pitch-deck PDF reading: one citable source per page.

Deck text is company-reported, so it is treated like a web page: fenced as untrusted data in
prompts and cited by page number.
"""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from deckbrief.models import Source

MAX_DECK_BYTES = 20_000_000
MAX_PAGES = 60
MAX_PAGE_CHARS = 4000


class DeckError(ValueError):
    """The file is not a readable PDF deck."""


def page_id(number: int) -> str:
    return f"deck p.{number}"


def read_deck(path: Path) -> list[Source]:
    if not path.exists():
        raise DeckError(f"deck not found: {path}")
    if path.stat().st_size > MAX_DECK_BYTES:
        raise DeckError("deck is larger than 20 MB")
    with path.open("rb") as fh:
        if fh.read(5) != b"%PDF-":
            raise DeckError("file is not a PDF")
    try:
        reader = PdfReader(path)
        if reader.is_encrypted:
            raise DeckError("deck is password protected")
        pages: list[Source] = []
        for i, page in enumerate(reader.pages[:MAX_PAGES], start=1):
            raw = page.extract_text() or ""
            lines = [" ".join(line.split()) for line in raw.splitlines()]
            text = "\n".join(line for line in lines if line)
            if text:
                first = text.splitlines()[0][:60]
                pages.append(
                    Source(
                        id=page_id(i),
                        kind="deck",
                        label=f"Deck page {i}: {first}",
                        text=text[:MAX_PAGE_CHARS],
                        page=i,
                    )
                )
    except DeckError:
        raise
    except (PdfReadError, OSError, ValueError, KeyError) as exc:
        raise DeckError(f"could not read PDF: {exc}") from exc
    if not pages:
        raise DeckError("no extractable text (scanned or image-only decks are not supported)")
    return pages
