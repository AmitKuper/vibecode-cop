"""CLI: fill the official submission form from league evidence.

    uv run --with python-docx --with docx2pdf python -m tools.submission_builder \
        --template ../submission/template.docx \
        --data ../submission/submission_data.json \
        --out ../submission [--no-pdf]
"""

from __future__ import annotations

import argparse
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from tools.submission_builder.builder import build_submission


def main() -> int:
    ap = argparse.ArgumentParser(prog="submission_builder")
    ap.add_argument("--template", required=True, help="official .docx template (outside the repo)")
    ap.add_argument("--data", required=True, help="submission_data.json (outside the repo)")
    ap.add_argument("--results", default="results", help="league results dir (default: results)")
    ap.add_argument("--out", required=True, help="output dir for the filled .docx/.pdf")
    ap.add_argument("--no-pdf", action="store_true", help="skip the Word->PDF conversion")
    args = ap.parse_args()
    result = build_submission(
        args.template, args.data, args.results, args.out, to_pdf=not args.no_pdf
    )
    print(f"docx: {result['docx']}")
    if result["pdf"]:
        print(f"pdf:  {result['pdf']}")
    if result["unfilled"]:
        print("WARNING - unfilled placeholders in the data file:")
        for item in result["unfilled"]:
            print("   ", item)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
