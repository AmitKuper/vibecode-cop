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

## 2026-08-20 — Anti-evader stall-squeeze hook (post-SMNGRP05 47-47)

Starting SHA `f9d79a1`. Committed the previously uncommitted hook after a
verification round that found and fixed two defects:

- `stall_squeeze._PLACE` was hand-typed in a rotated convention
  (`(-1,0)→PLACE_N` vs production `PLACE_N==(0,-1)`): every hook wall would
  have landed 90° off on the wire. Now derived from `action_space.PLACE_DIRS`
  and pinned by an exact-direction test (`PLACE_S` in the mirror state).
- The hook could fire at Manhattan distance 1 and preempt a capture-in-hand;
  added a `d <= 1` never-fire guard + test.

Evidence: `scripts/anti_evader_lab.py` (production `StallSqueeze` +
`best_cop_action`, production deltas) — mobility evader survival→capture@10,
hook silent where minimax already wins, mirror2 capture delayed 9→15 (same
outcome; known heuristic-trigger trade-off, never flipped an outcome);
peersim rehearsal `audits 6/6 ok` with cop captures @4/9/10; full suite
1952 passed / 4 skipped; ruff clean. Strength-guard after-pass: net cop
gain; residual risk = capture delay past step 35 in unobserved states,
bounded by strict improvement + 8-wall cap + `STALL_TURNS=4` (do not lower
without a wider variant matrix). Details: `docs/ANTI_EVADER_ANALYSIS.md`.

## 2026-08-20 — External (ChatGPT) review response: 3 submission items

Review scored 94/100; its three action items were verified against the tree
before acting (two were real, one was understated):

1. **Submission tag** — review said `v1.0-submission` was missing; actually
   it EXISTED in both repos but pointed at 2026-08-02 commits (pre-rebuild,
   pre-evidence) — worse than missing. Standardized: `v1.0-submission` (the
   book's checklist name) is THE graded tag, re-pointed to the final heads
   and force-pushed in both repos; `v2.0`/`v5.0-submission` demoted to
   historical milestones; both READMEs updated to say so.
2. **Step-0 evidence** — confirmed root causes in OUR writer
   (`league_artifacts/declaration.py`): `declared_at` was stamped with the
   series END (settlement-time write), and the opponent's
   `hardware_spec_sha256` was hard-coded `""` even when they transmitted a
   spec. Fixed (declared_at = series start; sha = theirs, else checksum of
   received spec) + 4 pins in `tests/test_declaration_step0_provenance.py`.
   bestteam's empty fields are what they actually transmitted — documented
   in `evidence/game_vs_bestteam/README.md` with pointers to the raw
   pre-play negotiate frames (runtime_match.log 01:19:05-08). Historical
   artifacts left untouched.
3. **KNOWN_DEVIATIONS contradiction** — confirmed (cop only): the "no
   browser screenshot of the live GUI" sentence contradicted the CLOSED
   entry above it; rewritten to point at `evidence/gui/`.

Review factual errors noted: it counted 7 counted series 6W-1L (ledger has
8: 6W-1L-1D incl. the SMNGRP05 draw) and said the tag was absent.

## 2026-08-21 — Overnight barrier-distillation experiment (research-only)

User-approved overnight experiment: can a net learn the barrier strategy?
`scripts/barrier_distill/` (teacher/thieves/collect/train/arena) — fully
firewalled (no MANIFEST/champion/serving change; artifacts in gitignored
results/barrier_distill/). 550 teacher episodes, two students (GRU + a
memoryless MLP), 4-policy arena. Result: both students exactly match the
search teacher's 22/28 (learned wall placement AND restraint); plain
minimax 20/28; nobody — teacher included — beats the future-wall-aware
minimax thief (0/4), consistent with the exact-solve draw value. Memory
hypothesis (stall timing needs a GRU) rejected: the MLP ties the GRU.
Recommendation recorded: keep search in production; experiment stands as
report evidence. Full writeup: docs/RL_BARRIER_EXPERIMENT.md.

## 2026-08-21 — yanell11 pairing: interop verified + sighted-under-book

New opponent (yanell11, kit-dialect doc). Verified their spec line-by-line
vs our code: seal/tools/terms/scent-law/settlement/uid/tie-add/timing all
byte-identical. Two reconciliation items sent in writing: (1) scent model —
AGREED multiplicative_book_v1 934c220d, both greetings declare it; (2) turn
order — their cop_first vs the kit's thief-first; sent verbatim kit
citations at be96e57 (PAIRING-PLAYBOOK L65/501, netplay.py:263,
turnloop.py docstring — which names bookletter-v3 `commit_order:
police_first` as the likely origin of their value and documents the kit's
own 2026-08-04 dogfood deadlock — series.py:124). Awaiting their written
thief-first confirmation before any window.

Sighted-under-book: locking book scent would have benched the sighted
minimax+stall-squeeze (chebyshev tracker reads only chebyshev frames).
Added `cop_worker/rl/opponent_fix.py`: exact inverse of the clamped book
law (scent_decoder, pinned 100% exact) accepted only on a UNIQUE consistent
cell, coasting otherwise; per-pairing switch via runtime.toml scent_model →
wrap_with_search → SearchRolePolicy(decode_book_scent). Both roles gain.
Chebyshev pairings byte-identical (decode off default). Gates: 5 new pins
in tests/test_sighted_under_book.py (incl. plateau-step action ==
best_cop_action on the TRUE cell), suite 1961/4, peersim rehearsal
6/6 (captures @7/6/8). Profile config/opponents/yanell11/ staged (Haifa
terms; URLs + operator inbox to fill from chat).
