# tools/submission_builder — the final-project Moodle form, built from evidence

## Why this is in the repo

The course requires a submission PDF built from the official Word template with
every field kept exactly in place, containing our league record (games, scores,
dates, opponents' declared counts, agent emails). Typing those numbers by hand
is how contradictions with the signed evidence happen — so this tool **derives
every game field from the same artifacts the agents exchanged on the wire**:

- `results/counted_series.json` — the league ledger (which games are legal);
- `results/result_<game>.json` — per-game signed results (scores, sub-game
  timestamps → Asia/Jerusalem times, opponents' `games_played_including_this`).

Only identity fields (IDs, names, self-score, opponents' agent emails) come
from a small JSON file, and that file — together with the official template and
the produced `vibecode-ex07.pdf` — deliberately lives **outside the repos**
(they carry personal data and are Moodle artifacts, not source code). The
*logic* lives here so it is versioned, reviewed, and tested like everything else.

## How it is used

```bash
cd vibecode-cop
uv run --with python-docx --with docx2pdf python -m tools.submission_builder \
    --template ../submission/template.docx \
    --data     ../submission/submission_data.json \
    --out      ../submission
```

Re-run **after every counted game** — the games table and totals (legal games,
points, won/lost/drawn) update themselves from the ledger. The command prints a
warning for any `<FILL:...>` placeholder still left in the data file, and the
produced PDF is verified with `tools/pdf_parser` (`read` / `search`).

## How it works

- `builder.py` — `load_games()` / `compute_totals()` (pure, tested against a
  synthetic ledger), `build_submission()` which fills the template via
  `tools.pdf_parser.docx_form.fill_docx_form` (append-only run edits — fields
  never move) and converts with MS Word (`docx_to_pdf`).
- `FIELD_PARAGRAPHS` / `NAME_PARAGRAPHS` pin the official template's paragraph
  indices in one reviewed place.
- Tests: `tests/test_submission_builder.py` (offline; docx tests auto-skip when
  `python-docx` isn't installed — run them with `uv run --with python-docx`).
