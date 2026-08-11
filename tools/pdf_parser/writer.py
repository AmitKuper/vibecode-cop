"""Write side: minimal, dependency-free text-PDF generator.

Produces standards-conform single-font (Helvetica) PDFs good enough for reports
and evidence exports; round-trip verified against the pypdf reader in
tests/test_pdf_parser.py. Not a layout engine — long lines are wrapped at a
character budget and long documents flow onto extra pages automatically.
"""

from __future__ import annotations

from pathlib import Path

PAGE_W, PAGE_H = 612, 792  # US Letter, points
MARGIN = 54
FONT_SIZE = 11
TITLE_SIZE = 16
LEADING = 15
CHARS_PER_LINE = 92
LINES_PER_PAGE = (PAGE_H - 2 * MARGIN - 2 * LEADING) // LEADING


def _escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _wrap(paragraphs: list[str]) -> list[str]:
    lines: list[str] = []
    for para in paragraphs:
        for raw in para.splitlines() or [""]:
            words, current = raw.split(" "), ""
            for word in words:
                candidate = f"{current} {word}".strip()
                if len(candidate) <= CHARS_PER_LINE:
                    current = candidate
                else:
                    lines.append(current)
                    current = word
            lines.append(current)
        lines.append("")
    while lines and not lines[-1]:
        lines.pop()
    return lines


def _page_stream(title: str | None, lines: list[str]) -> bytes:
    parts = ["BT"]
    y = PAGE_H - MARGIN
    if title is not None:
        parts.append(f"/F1 {TITLE_SIZE} Tf 1 0 0 1 {MARGIN} {y} Tm ({_escape(title)}) Tj")
        y -= 2 * LEADING
    parts.append(f"/F1 {FONT_SIZE} Tf 1 0 0 1 {MARGIN} {y} Tm {LEADING} TL")
    for line in lines:
        parts.append(f"({_escape(line)}) Tj T*")
    parts.append("ET")
    return "\n".join(parts).encode("latin-1", "replace")


def write_text_pdf(path: str | Path, title: str, paragraphs: list[str]) -> Path:
    """Write ``paragraphs`` under ``title`` to ``path``; returns the path."""
    lines = _wrap(list(paragraphs))
    pages = [lines[i : i + LINES_PER_PAGE] for i in range(0, len(lines), LINES_PER_PAGE)] or [[]]
    objects: list[bytes] = []
    page_object_numbers = [4 + 2 * i for i in range(len(pages))]
    kids = " ".join(f"{n} 0 R" for n in page_object_numbers)
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for index, page_lines in enumerate(pages):
        stream = _page_stream(title if index == 0 else None, page_lines)
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] "
                f"/Resources << /Font << /F1 3 0 R >> >> /Contents {5 + 2 * index} 0 R >>"
            ).encode()
        )
        objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream")
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets[1:]:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n"
    ).encode()
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(bytes(out))
    return target
