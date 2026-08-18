# Execution plan & evidence ledger — score-100 track

The running record mandated by the workspace CLAUDE.md: what was executed,
under which commits, with what result, and where the evidence lives. Every
number here is derived from `results/counted_series.json` and the per-game
artifacts, not typed from memory. (This file was reconstructed 2026-08-19
after an earlier docs purge removed it; the underlying evidence was never
lost.)

## Counted league record — 7 series, 6W–1L, 575 points

| # | Date | Series | Score | Winner | Report message-id |
|---|------|--------|-------|--------|-------------------|
| 1 | 2026-08-08 | anrbj666-vs-vibecode | 35–75 | anrbj666 | 19fe2cdea7a51125 |
| 2 | 2026-08-10 | imreeyal-vs-vibecode | 90–30 | vibecode | 19fecf55c1b5eea0 |
| 3 | 2026-08-11 | uoh-sqak-vs-vibecode | 90–30 | vibecode | 19ff3140bfdfea7c |
| 4 | 2026-08-14 | rstabcde-vs-vibecode | 90–30 | vibecode | 1a000e76ccd62963 |
| 5 | 2026-08-14 | najamjad-vs-vibecode | 90–30 | vibecode | 1a001a7f77c911c3 |
| 6 | 2026-08-16 | nis-yar1-vs-vibecode | 90–30 | vibecode | 1a00c1363a39a870 |
| 7 | 2026-08-18 | bestteam-vs-vibecode | 90–30 | vibecode | 1a016f83951523c1 |

Every counted report went ONLY to the league address; each `.eml` (ours and
the opponent's forwarded copy where obtained) is preserved under
`evidence/game_vs_<opponent>/`. `min_games_to_pass = 2` is satisfied 7×.

## Standard per-game production path (proven end-to-end every series)

```
scripts/live_match_ref3.py --match --config <opponent> \
    [--counted --counted-played N --report-to <league address>]
```

CLI → COUNTED runtime → split-arch orchestrator (one OS process per role) →
signed bilateral Step-0 (terms + scent/wire locks + identity) → six
sub-games → commit-reveal per turn → mutual comprehensive audit → signed
result consensus → league ledger → independent Gmail report. The settlement
guard (`scripts/ref3_match/report_guard.py`) withholds the report on
anything short of a clean 6/6.

## Per-game evidence layout

- `evidence/game_vs_<opponent>/` — role-split gamelet artifacts
  (config+log+record), declaration, result, ledger snapshot, filed report
  `.eml`(s), runtime log, README.
- Tags `game_vs_<opponent>` mark the game commit; branches
  `backup-YYYYMMDD-<opponent>-counted` preserve the closed state (from
  uoh-sqak onward; earlier games are covered by their tags).
- `artifacts/game_vs_bestteam_live/` — operator screen recording +
  screenshot of the live GUI captured DURING counted game 7.

## Key decisions on the record (with the commit or thread that fixed them)

- **Scent**: `subtractive_chebyshev_v1` (lock 81ebee59…) locked at Step-0
  in every series; movement is `hybrid_search` minimax over an exact
  chebyshev tracker (nets are the blind-frame fallback).
- **config_sha256 follows the `--config` profile** (fixed 2026-08-18 after
  six series silently declared the base file's stale `agreed_between`;
  pinned by `tests/test_declared_constitution_follows_profile.py`).
- **Consensus-hash scope is outcome-only**, so equal scorelines collide
  across series (observed: identical mutual sha across three
  bestteam series, predicted in writing by the opponent pre-game).
  Discriminator: `game_uid` + per-row timestamps + declared commits.
- **Repos remained private throughout league play** — renegotiated in
  writing with bestteam (rule 53 binds the declaring, not anonymous
  resolvability); per-role heads are declared in every Step-0.
- **Friendlies report only between operators**, never the lecturer;
  counted reports are single-recipient to the league address (enforced:
  the address is never stored in config, only passed via `--report-to`).

## Verification commands

```
python -m pytest -q                      # full suite
python scripts/check_file_size.py        # 150-line ratchet
python -m ruff check . && python -m ruff format --check .
python scripts/preflight_opponent.py <url> [...]   # peer surface probe
```

Final submission tag: deferred until the operator declares the project
final; the `game_vs_*` tags and backup branches carry the per-game truth
until then.
