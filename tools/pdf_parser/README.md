# tools/pdf_parser — read and write PDF files

Small, tested PDF toolkit used for consuming course documents (rule books,
briefs) and producing report/evidence exports.

- **Reading** is backed by [`pypdf`](https://pypi.org/project/pypdf/) (declared
  in `pyproject.toml`): per-page text extraction, metadata, and text search.
- **Writing** is a self-contained minimal PDF 1.4 generator (Helvetica, US
  Letter, automatic word-wrap and multi-page flow) with zero extra
  dependencies; its output is round-trip verified against the pypdf reader.

## Python API

```python
from tools.pdf_parser import (
    read_pdf_text,      # (path, page=None) -> list[str], one string per page
    read_pdf_metadata,  # (path) -> dict incl. "pages"
    search_pdf,         # (path, needle, ignore_case=True) -> [{page, line_number, line}]
    write_text_pdf,     # (path, title, paragraphs) -> Path
    PdfParserError,     # raised for missing/garbage files, bad pages, empty search
)

write_text_pdf("out/report.pdf", "Match Report", ["Cop won 90-30.", "Audits 6/6."])
pages = read_pdf_text("out/report.pdf")
hits = search_pdf("../project docs/police_thief_p2p.pdf", "pheromone")
```

## CLI

```bash
python -m tools.pdf_parser read  file.pdf [--page N]        # extracted text
python -m tools.pdf_parser meta  file.pdf                   # metadata JSON
python -m tools.pdf_parser search file.pdf "pheromone"      # page:line hits
python -m tools.pdf_parser write out.pdf --title "T" --text "para one" --text "para two"
python -m tools.pdf_parser write out.pdf --title "T" --from-file notes.txt
```

Console output is forced to UTF-8 (course PDFs contain Hebrew).

## Real-world use: the final-project submission PDF

This toolkit is part of the submission workflow (the submission artifacts
themselves are deliberately kept outside the repos):

1. **Parsing the course documents** — extracting the scent-law specification
   from `police_thief_p2p.pdf` and reading the official submission template's
   field layout (`read` / `search` subcommands).
2. **Mining prior submissions** — pulling student identity fields out of the
   earlier `vibecode-ex0N.pdf` files so the final form is consistent with them.
3. **Generating the submission** — `docx_form.py` (this package) fills the
   official Word template append-only (field positions never move) and converts
   it to PDF; the course-specific field mapping lives in
   `tools/submission_builder/`.
4. **Verifying the generated submission** — the produced `vibecode-ex07.pdf`
   is read back with this tool and checked field-by-field (group id, repos,
   agent email, game table rows, totals) against the league ledger in
   `results/counted_series.json`.

## Limits (by design)

- The writer is a text-report generator, not a layout engine: one font, no
  images, lines wrapped at a fixed character budget.
- Extraction quality of third-party PDFs is whatever `pypdf` achieves; scanned
  (image-only) documents yield empty text.

## Tests

`tests/test_pdf_parser.py` — 9 offline tests: write→read round-trip, escaping
of `( ) \`, multi-page flow, wrap budget, metadata/page selection, search
(case both ways, page+line reporting), missing/garbage-file rejection, and CLI
coverage for every subcommand.
