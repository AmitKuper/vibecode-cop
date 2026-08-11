"""CLI: read, inspect, search, and write PDFs.

python -m tools.pdf_parser read <file.pdf> [--page N]
python -m tools.pdf_parser meta <file.pdf>
python -m tools.pdf_parser search <file.pdf> <text>
python -m tools.pdf_parser write <out.pdf> --title T --text "para" [--text "para2"]
python -m tools.pdf_parser write <out.pdf> --title T --from-file notes.txt
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tools.pdf_parser.reader import read_pdf_metadata, read_pdf_text, search_pdf
from tools.pdf_parser.writer import write_text_pdf


def main(argv: list[str] | None = None) -> int:
    # Windows consoles default to cp1252; PDFs routinely carry Unicode (e.g. Hebrew).
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(prog="pdf_parser")
    sub = ap.add_subparsers(dest="command", required=True)

    p_read = sub.add_parser("read", help="print extracted text")
    p_read.add_argument("path")
    p_read.add_argument("--page", type=int, default=None, help="1-based single page")

    p_meta = sub.add_parser("meta", help="print metadata as JSON")
    p_meta.add_argument("path")

    p_search = sub.add_parser("search", help="find text; prints page:line hits")
    p_search.add_argument("path")
    p_search.add_argument("needle")
    p_search.add_argument("--case-sensitive", action="store_true")

    p_write = sub.add_parser("write", help="create a text PDF")
    p_write.add_argument("path")
    p_write.add_argument("--title", required=True)
    p_write.add_argument("--text", action="append", default=[], help="paragraph (repeatable)")
    p_write.add_argument("--from-file", type=Path, help="read paragraphs from a UTF-8 text file")

    args = ap.parse_args(argv)
    if args.command == "read":
        for number, text in enumerate(read_pdf_text(args.path, args.page), start=args.page or 1):
            print(f"--- page {number} ---")
            print(text)
    elif args.command == "meta":
        print(json.dumps(read_pdf_metadata(args.path), indent=1))
    elif args.command == "search":
        hits = search_pdf(args.path, args.needle, ignore_case=not args.case_sensitive)
        for hit in hits:
            print(f"p{hit['page']}:{hit['line_number']}: {hit['line']}")
        print(f"{len(hits)} hit(s)")
    elif args.command == "write":
        paragraphs = list(args.text)
        if args.from_file:
            paragraphs.extend(args.from_file.read_text(encoding="utf-8").split("\n\n"))
        if not paragraphs:
            ap.error("write needs --text and/or --from-file")
        target = write_text_pdf(args.path, args.title, paragraphs)
        print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
