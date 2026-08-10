# Test Evidence — vibecode-cop

Current as of **2026-08-10**, working tree at HEAD `3ab6e1f`. This file records what
was actually measured and where the artifacts live; the strategy behind the suite is
`docs/TESTING.md`. (Earlier phase-0/0.5 baselines from the pre-restructure `agent/`
era were removed as stale; they remain in git history.)

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

Result: **1,484 passed, 1 skipped** at the measured coverage run (~3 min locally);
a same-day re-run after the in-progress coverage push collected **1,540 tests
(1,539 passed, 1 skipped)** — the suite is actively growing toward the 85% target.
The single skip is `tests/reference_v3/test_survival_terminal.py`
(`thief_worker not on path` — cross-repo test, runs when the sibling
`vibecode-thief` checkout is importable); nothing is ignored via `addopts`.

## Coverage

Command (identical to the CI gate in `.github/workflows/ci.yml`):

```bash
uv run pytest tests/ cop_worker/tests/ league_manager/tests/ \
  --cov=cop_worker --cov=league_manager --cov-branch \
  --cov-report=xml --cov-fail-under=80
```

Result: **80.85% branch coverage** (11,131 statements / 2,754 branches measured) —
gate ≥ 80% passed. Branch coverage is stricter than line coverage (line is ~85%);
the enforced floor is 80 in both CI and `pyproject.toml` (`fail_under = 80`), with
85 as the tracked target (see `docs/TESTING.md`).

CI also enforces: `uv lock --check`, `ruff check`, `ruff format --check`, and a
secret scan — all green on `master`.

## Protocol conformance evidence

- **Kit vectors, full run:** `python verify_vectors.py` from the unmodified
  `copthief-league-protocol` checkout at commit **`be96e57`** —
  **125 checks / 15 fixtures (7 CORE, 4 PROMOTED, 2 PROPOSED, 2 ENH): ALL PASS**.
  Driven by `scripts/verify_reference_v3_interop.py`, which refuses to run against a
  dirty kit tree.
- **Ported vectors, every pytest run:** `tests/test_scent_chebyshev.py` carries the
  kit's `vectors/pheromone.json` (CORE) fixture bytes verbatim (pinned at `be96e57`),
  so scent-arithmetic drift fails CI without importing the kit;
  `tests/reference_v3/test_game_uid_vectors.py` and
  `tests/test_scent_model_negotiation.py` pin uid derivation and the `SCENT_LOCKS`
  hashes on the wire.

## Live evidence chain (the tests that were played, not run)

The counted ledger (`evidence/game_vs_imreeyal/counted_series.json`) records
`counted_games_played: 2`, two distinct opponents — the league's
`min_games_to_pass = 2` satisfied. Each counted series was preceded by friendly
rehearsal series with the same opponent over the same wire path (friendlies default
to the own-inbox report and increment no counter).

| Series | Date | Result | Audits | Artifacts |
|---|---|---|---|---|
| Friendly rehearsals vs anrbj666, then vs imreeyal | 2026-08-05 .. 2026-08-10 | rehearsal outcomes; surfaced the bugs now pinned in `tests/` (episode reset, empty timestamp, capture-claim initiation, enclosure duty) | 6/6 `Verified OK` per completed series | `reports/ref3_matches/` logs; per-opponent profile saved to `config/opponents/<opp>/` |
| **Counted vs anrbj666** | 2026-08-08 | loss 35–75 (sub-games 1–5) | **6/6 `Verified OK`**, mutual agreement `b4db10c2…` confirmed | `evidence/game_vs_anrbj666/` (declaration, per-gamelet config+log, result, ledger, filed report `.eml`, msg-id `19fe2cdea7a51125`) |
| **Counted vs imreeyal** | 2026-08-10 | **win 90–30 (sub-games 6–0)** | **6/6 `Verified OK` both directions**, mutual agreement `ad403f44…` confirmed | `evidence/game_vs_imreeyal/` (declaration, configs, logs, result, `runtime_match.log` full wire log, authorization, report `.eml`, msg-id `19fecf55c1b5eea0`) |

Series facts for the counted win: `game_uid 2e167349-f579-0201-e3f1-5ea0d75710c0`,
scent lock `subtractive_chebyshev_v1` (`81ebee59…`), `[row, col]` wire cells, commit
SHAs exchanged in writing pre-T (ours: cop `14a7ddf…`, thief `06c2cf2…`). Outcomes:
our thief SURVIVAL g01/g03/g05 (35 rounds each); our cop CAPTURE g02/g04/g06.
Reports were emailed independently by both teams to the league address at
settlement.

The point of this table: every claim in the conformance and unit sections above was
also exercised against two real, independently implemented opponents, with
commit-reveal audits verifying every sealed record in both directions.
