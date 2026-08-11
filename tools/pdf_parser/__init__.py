"""PDF read/write toolkit — see tools/pdf_parser/README.md.

Public surface:
    read_pdf_text(path, page=None) -> list[str]
    read_pdf_metadata(path) -> dict
    search_pdf(path, needle, ignore_case=True) -> list[dict]
    write_text_pdf(path, title, paragraphs) -> Path
"""

from tools.pdf_parser.reader import (
    PdfParserError,
    read_pdf_metadata,
    read_pdf_text,
    search_pdf,
)
from tools.pdf_parser.writer import write_text_pdf

__all__ = [
    "PdfParserError",
    "read_pdf_metadata",
    "read_pdf_text",
    "search_pdf",
    "write_text_pdf",
]
