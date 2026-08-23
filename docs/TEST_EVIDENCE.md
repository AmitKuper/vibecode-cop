# Test Evidence — vibecode-cop

Current as of **2026-08-15**. This file records what was actually measured and where
the artifacts live; the strategy behind the suite is `docs/TESTING.md`. (Earlier
phase-0/0.5 baselines from the pre-restructure `agent/` era — a package that no
longer exists — were removed as stale; they remain in git history.)

## Environment

| Item | Value |
|---|---|
| Python | 3.13 (CPython) |
| Platform | Windows 11 Pro 10.0.26200 (CI: ubuntu-latest) |
| Toolchain | uv (locked via `uv.lock`), pytest 9.x, coverage 7.x, ruff |

## Suite result

Command:

```bash
uv run pytest tests/ cop_worker/tests/ league_manager/tests/ -q --tb=short
```

Result: **1,887 passed, 4 skipped** in 88.69 s (1,891 collected). The four skips are
environment-conditional, never defects: `tests/reference_v3/test_survival_terminal.py`
(`thief_worker not on path` — cross-repo test, runs when the sibling
`vibecode-thief` checkout is importable) and three `python-docx not installed in
this venv` skips in `tests/test_pdf_parser_docx.py` (2) and
`tests/test_submission_builder.py` (1), which cover the `tools/` submission helpers
rather than the match runtime. Nothing is ignored via `addopts`.

## Coverage

Command (identical to the CI gate in `.github/workflows/ci.yml`):

```bash
uv run pytest tests/ cop_worker/tests/ league_manager/tests/ \
  --cov=cop_worker --cov=league_manager --cov-branch \
  --cov-report=xml --cov-fail-under=94
```

Result: **96.18% branch coverage** (24,199 statements / 3,056 branches measured,
re-measured 2026-08-19 with 1,942 passed / 4 skipped; the 2026-08-15 audit read
94.90%) — gate ≥ 94% passed. Branch coverage is stricter than line coverage;
the enforced floor is 94 in both CI and `pyproject.toml` (`fail_under = 94`), which
is above the course guideline target of 85 (see `docs/TESTING.md`).

CI also enforces: `uv lock --check`, `ruff check`, `ruff format --check`, and a
secret scan — all green on `master`.

## Protocol conformance evidence

- **Kit vectors, full run:** `python verify_vectors.py` from the unmodified
  `copthief-league-protocol` checkout at commit **`be96e57`** —
  **125 checks / 15 fixtures (7 CORE, 4 PROMOTED, 2 PROPOSED, 2 ENH): ALL PASS**.
  Driven by `scripts/verify_reference_v3_interop.py`, which refuses to run against a
  dirty kit tree.
- **Ported vectors, every pytest run:** `tests/test_scent_chebyshev.py` carries the
  kit's `vectors/pheromone.json` (CORE) fixture bytes verbatim — in a sibling
  checkout, `../external/copthief-league-protocol/vectors/pheromone.json`
  (pinned at `be96e57`) —
  so scent-arithmetic drift fails CI without importing the kit;
  `tests/reference_v3/test_game_uid_vectors.py` and
  `tests/test_scent_model_negotiation.py` pin uid derivation and the `SCENT_LOCKS`
  hashes on the wire.

## Live evidence chain (the tests that were played, not run)

The counted ledger (`results/counted_series.json`) records
`counted_games_played: 10` against ten distinct opponents — the league's
`min_games_to_pass = 2` (`config/game.json`) satisfied more than twice over. Counted
series were preceded by friendly rehearsals over the same wire path (friendlies
default to the own-inbox report and increment no counter).

| Series | Date | Result | Audits | Artifacts |
|---|---|---|---|---|
| **Counted vs anrbj666** | 2026-08-08 | loss 35–75 (sub-games 1–5) | 6/6 `Verified OK`, mutual agreement `b4db10c2…` confirmed | `evidence/game_vs_anrbj666/`, msg-id `19fe2cdea7a51125` |
| **Counted vs imreeyal** | 2026-08-10 | **win 90–30 (6–0)** | 6/6 `Verified OK` both directions, mutual agreement `ad403f44…` confirmed | `evidence/game_vs_imreeyal/`, msg-id `19fecf55c1b5eea0` |
| **Counted vs uoh-sqak** | 2026-08-11 | **win 90–30 (6–0)** | 6/6 `Verified OK`, mutual agreement `dfb41c7d…` confirmed | `evidence/game_vs_uoh-sqak/`, msg-id `19ff3140bfdfea7c` |
| **Counted vs rstabcde** | 2026-08-14 | **win 90–30 (6–0)** | 6/6 `Verified OK`, mutual agreement `b220c636…` confirmed | `evidence/game_vs_rstabcde/`, msg-id `1a000e76ccd62963` |
| **Counted vs najamjad** | 2026-08-14 | **win 90–30 (6–0)** | 6/6 `Verified OK`, mutual agreement `041880e5…` confirmed | `evidence/game_vs_najamjad/`, msg-id `1a001a7f77c911c3` |

Each series directory carries the signed declaration, the `config_*`/`log_*`
artifacts for this repo's three cop windows (g02/g04/g06 — the thief windows are
published in `vibecode-thief`), the result JSON, and the filed report `.eml` (ours
to the lecturer plus the opponent's copy); every series except anrbj666 also keeps
its full `runtime_match.log`. Friendly rehearsals surfaced the bugs now
pinned in `tests/` (episode reset, empty timestamp, capture-claim initiation,
enclosure duty); their logs are in `reports/ref3_matches/` and each opponent's
effective config is saved to `config/opponents/<opp>/`.

Series facts for the first counted win: `game_uid 2e167349-f579-0201-e3f1-5ea0d75710c0`,
scent lock `subtractive_chebyshev_v1` (`81ebee59…`), `[row, col]` wire cells, commit
SHAs exchanged in writing pre-T (ours: cop `14a7ddf…`, thief `06c2cf2…`). Outcomes:
our thief SURVIVAL g01/g03/g05 (35 rounds each); our cop CAPTURE g02/g04/g06.
Reports were emailed independently by both teams to the league address at
settlement.

The point of this table: every claim in the conformance and unit sections above was
also exercised against five real, independently implemented opponents, with
commit-reveal audits verifying every sealed record in both directions.
