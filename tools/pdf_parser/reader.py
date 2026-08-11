"""Read side: text extraction, metadata, and search over PDF files (pypdf-backed)."""

from __future__ import annotations

from pathlib import Path


class PdfParserError(ValueError):
    """Raised for unreadable files or out-of-range pages."""


def _reader(path: str | Path):
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    p = Path(path)
    if not p.is_file():
        raise PdfParserError(f"not a file: {p}")
    try:
        return PdfReader(str(p))
    except PdfReadError as exc:
        raise PdfParserError(f"unreadable PDF {p}: {exc}") from exc


def read_pdf_text(path: str | Path, page: int | None = None) -> list[str]:
    """Extract text per page. ``page`` is 1-based; None returns every page."""
    reader = _reader(path)
    total = len(reader.pages)
    if page is not None:
        if not 1 <= page <= total:
            raise PdfParserError(f"page {page} out of range 1..{total}")
        return [reader.pages[page - 1].extract_text() or ""]
    return [p.extract_text() or "" for p in reader.pages]


def read_pdf_metadata(path: str | Path) -> dict:
    """Document metadata plus page count; values are plain strings."""
    reader = _reader(path)
    meta = reader.metadata or {}
    out = {str(k).lstrip("/").lower(): str(v) for k, v in meta.items() if v is not None}
    out["pages"] = len(reader.pages)
    return out


def search_pdf(path: str | Path, needle: str, ignore_case: bool = True) -> list[dict]:
    """Find ``needle`` across pages; returns [{page, line_number, line}, ...]."""
    if not needle:
        raise PdfParserError("empty search string")
    probe = needle.lower() if ignore_case else needle
    hits: list[dict] = []
    for page_number, text in enumerate(read_pdf_text(path), start=1):
        for line_number, line in enumerate(text.splitlines(), start=1):
            haystack = line.lower() if ignore_case else line
            if probe in haystack:
                hits.append({"page": page_number, "line_number": line_number, "line": line.strip()})
    return hits
