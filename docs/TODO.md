# TODO — vibecode-cop

Last updated: 2026-08-15.

The pre-restructure phase log that used to live here described the `agent/` package
(board, rules engine, crewAI orchestrator, PPO/DQN trainers). That package has been
deleted and none of those paths exist; the log remains in git history. Accepted
deviations are tracked separately in `docs/KNOWN_DEVIATIONS.md`.

## Current state (verified)

- [x] Production runtime is `--arch split`: the orchestrator
      (`scripts/ref3_match/series_split.py`) spawns one OS process per role via
      `scripts/ref3_role_worker.py` (Appendix E rules 1–2; DESIGN AD-1).
- [x] Seven counted series played and settled (`results/counted_series.json`,
      `counted_games_played: 5`): lost 35–75 vs anrbj666; won 90–30 vs imreeyal,
      uoh-sqak, rstabcde and najamjad. 6/6 mutual audits `Verified OK` each, every
      report emailed and filed under `evidence/game_vs_*/`.
- [x] Suite green: 1,887 passed / 4 skipped, **94.90%** branch coverage against a
      CI gate of 94 (`pyproject.toml` `fail_under = 94`,
      `.github/workflows/ci.yml --cov-fail-under=94`).
- [x] `ruff check` + `ruff format --check` clean and CI-gated.
- [x] `config/runtime.toml` carries a `[protocol]` block
      (`subtractive_chebyshev_v1` + `hybrid_search`), so a profile-less run uses
      the pairing defaults we actually play on.
- [x] Promoted cop champion pinned in `models/MANIFEST.json`
      (`cop_chebyshev_champion.pt`), with the obs-mode serving guard refusing any
      mismatched load.

## Open

- [ ] **Seven modules still exceed the 150-line rule** — listed with rationale in
      `docs/KNOWN_DEVIATIONS.md` D4. The transition function is a deliberate
      permanent exception; the six others are splittable after the league window.
- [ ] **`cop_worker/` ↔ `league_manager/` duplication** — most copies are now
      import aliases; finish the collapse once no more league windows are possible
      (DESIGN AD-9, `docs/KNOWN_DEVIATIONS.md` D6).
- [ ] **No committed browser screenshot of the live GUI**
      (`docs/KNOWN_DEVIATIONS.md` D5).
- [ ] **Course submission** — final Moodle upload, official identity fields, and
      pushed release tags are external actions, not code gates.
