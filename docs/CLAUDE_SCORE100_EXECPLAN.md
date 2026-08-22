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

## 2026-08-21 — opp-W pairing: interop verified + sighted-under-book

New opponent (internally "opp-W" — the name is withheld from the repo
until a counted game with them concludes; kit-dialect doc). Verified
their spec line-by-line
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
6/6 (captures @7/6/8). Opponent profile staged locally OUTSIDE the repo
tree (Haifa terms; URLs + operator inbox to fill from chat).

## 2026-08-21 (later) — opp-W: thief-first CONFIRMED; series-label folding shipped

opp-W verified our kit citations upstream and CONFIRMED
`turn_order = thief_first` in writing (they flip their engine + re-gate
their strategy; sparring-peer dry-run on their side; they ping with an
endpoint + window in ~2 days). Scent stays locked book/934c220d. Ack sent
(ack reply, kept off-repo) incl. a sequencing tell for their dry-run.

Shipped kit §5 series-label folding end to end: derive_game_id/uid take an
optional label (labeled uid seeds on the LABELED game_id; unlabeled bytes
unchanged — pinned), build/verify_negotiation fold + REFUSE a label
disagreement (SPAR-N10), plumbed config [protocol] series_label →
cli --series-label → both play paths → role worker → handshake →
artifacts_io. 5 pins in tests/test_series_label_uid.py; suite 1966/4;
size-gate allowances bumped with justification (subgame_setup 170,
series_split 155); peersim rehearsal 6/6 on the unlabeled default.

## 2026-08-21 (night) — anti-squeeze thief (opp-W postmortem response)

Friendly vs opp-W: LOST all 4 played windows (60-20; sg1-2 burned on
their stale-driver desync, report withheld). Postmortem from sealed
records: NO bugs on our side (decoder exact 120/120 vs audit-true
positions; live chase correct; claims-convention consistent) — outplayed
by a deterministic scripted line-partition cop (guard col, wall line with
one self-door, cross, pocket; identical move-for-move g03/g05) and a
scripted evader thief.

Counter shipped: confined-mode thief (`cop_worker/rl/line_escape.py` +
thief-branch hook in search_policy). Trigger: any interior row/col line
with >= 2 walls completable within the cop's remaining budget. Mode: exact
current-walls survival table + MOBILITY tie-break (the SMNGRP05-evader
style) — measured the only survivor of the sweep (minimax d4/d6/d8 all die
@26; pessimistic-completion tables are blind to future pocket walls; the
crossing-tempo override oscillates). Lab `scripts/line_sweep_lab.py`:
sweep-cop clone (line phase from their records + minimax hunt = stronger
than their actual cop) — escape OFF captured @26 (reproduces the loss),
escape ON SURVIVES (mode active 24 turns). 8 pins in test_line_escape.py;
suite 1974/4; peersim rehearsal 6/6 (trigger silent vs normal cops —
byte-identical minimax without a line threat). Known trade-off documented:
a stall-squeeze-style cop can trip the trigger and evader mode is
wall-myopic — but the minimax thief already loses to such cops, floor
holds. Open offensive half: corridor-planner cop (their strategy, ours to
industrialize) — required before any counted-game consideration vs
opp-W.

## 2026-08-22 — learned-player program Phase 1 (operator-directed)

Operator goal shift: a player whose match-time decisions come from learned
weights (algorithms as training-time teachers only). Phase 1 = full-stack
distillation BOTH roles: thief teacher = minimax + confined-mode; thief
corpus 400 episodes vs randomized sweep-cop curriculum (teacher survived
400/400 incl. vs our own hook cop). Students (GRU + MLP, both roles):
match the teacher everywhere measurable, and BOTH thief students SURVIVE
the sequential sweep-cop acid test where minimax d4/d6/d8 die @26 — the
learned thief beats the strategy that beat us live, weights-only. Harness
honesty: the joint-action thief arena proved non-discriminating (even
minimax survives under simultaneous moves); conclusions rest on the
sequential line_sweep_lab. Writeup docs/RL_PLAYER_PROGRAM.md. Phases 2
(RL fine-tune from distilled init) and 3 (gated promotion, friendlies
first) defined. Production untouched.

## 2026-08-22 — corridor-planner cop (offensive half, operator-directed)

`cop_worker/rl/corridor_plan.py` + priority wiring in search_policy (cop:
corridor > stall-squeeze > minimax). opp-W's line-partition strategy
industrialized: on a sustained CLOSE oscillation (6 turns, d 2..6, spread
<=1, step>=8, budget>=9) the plan builds a wall line 2 cells off the thief
on the widest axis from a guard lane, seals to ONE door, then goes silent —
minimax + stall-squeeze hunt the strip (the combination that captured our
own thief @26 in the lab). corridor_lab matrix: mirror2 (near-perfect
evader) survival -> CAPTURE @30; zero regression (distance/center/away
identical; mobility same outcome, slower — plan preempts the quicker
squeeze kill, documented); confined + minimax thieves still survive
(consistent with exact theory: no forced 35-step win vs wall-aware
defense). Trigger hardened twice: spread<=1 (never a slow close),
max(recent)<=6 (a far thief is not evading — caught by the sighted-book
test). 7 pins in test_corridor_plan.py; suite 1980/4; peersim 6/6
(captures @5/@6 — trigger silent vs weak thieves). Rematch projection vs
opp-W same brains: WIN if their thief is wall-myopic (mirror2-class),
DRAW if confined-quality; loss requires an unseen strategy.

## 2026-08-22 overnight — operator-driven strength program (pre-vm__fabi)

Operator (playing both roles in the GUI) exposed and drove fixes for four
thief kill patterns and one cop gap. All work gated by the deterministic
lab battery (5s search budgets, idle CPU — 1s budgets under load produced
false verdicts, corrected in db8a5a5) plus the full suite and a peersim
rehearsal per production-affecting commit.

| Commit | What | Evidence |
|---|---|---|
| 628f6db | Thief: sealability min-cut + turn-parity fix in confined-mode survival | pocketer lab: pocket survival; suite 1843; peersim 6/6 |
| e65b8a8 | Thief: wall-safe one-ply lookahead (corner-seal counter) | line-hunt lab arm; suite 1845; peersim 6/6 |
| 5fdd37a/69fb5dd | RL: operator strategies as training pool + arena opponents | v8/v9 trained; arena: search 20/20 > v7 18/20 > v8 16/20 > v9 14/20 (imitation ceiling; no promotion) |
| 1ff0ed4 | Thief: cop-blocked min-cut (cage-cork counter) + seal-gated survival | cage lab arm; suite 1846; peersim 6/6 |
| db8a5a5 | Labs made deterministic (5s budgets); verdict corrections on record | pocketer 3x2 idle truth |
| (tonight) | Cop: CommittedHunt plan (operator playbook) — GUI chain + COPTHIEF_HUNT_MODE opt-in; wire default stays corridor | corridor_lab 3-column matrix; hunt captures confined @31 (first cop to beat our own thief class); suite 1856 |

Open, documented as theory-bound: the minimax-dance thief survives every
cop chain; the full-depth line-hunt/cage cops beat every thief (7x7 with
14 walls appears cop-favored under strong play; the operator converged on
the winning strategy class independently).

## 2026-08-22 — COUNTED #9 vs vm__fabi: WON 90-30 (ledger 7W-1L-1D)

Launched 16:24:38 on written authorization (rule 52: their declaration +
our quote-back, T amended in writing to "fire whenever ready"). 6/6 audits,
max score every window (thief survival g1/g3/g5, cop capture g2/g4/g6).
Commits played: cop 043e4fdd / thief 038ec0aa (pushed) vs their cabcb074.
Our report id 1a029a8052a59583 to rmisegal+uoh26finalgame@gmail.com
(single recipient, verified in Sent). Rule 35 CLOSED same hour: mutual
.eml forwards (ours 1a029ace4aad094c, theirs 1a029ae9dd72a7e1); their
report reconciles byte-level (uid 6268e7d5, 90-30, mutual sha c307dc51,
league-address-only). Evidence + emls committed both repos, tag
game_vs_vm__fabi, backup branch backup/post-vm__fabi-counted, PDF row 9.

## 2026-08-23 — COUNTED #10 vs cosmos77: DRAW 47-47 (ledger 7W-1L-2D) + submission freeze

Friendly settled 47-47 (six survivals; rows 45-45 + tie rule). Counted took
FOUR launches, four root causes closed (two per side):
1) 22:42 + 23:16 attempts withheld 5/6 — their sg1 receive_turn refused x6
   then 404. Their "file the 5/6" proposal DECLINED: zeroed w1 scores 40-35
   to them, and their claim our engine co-signed sha 130897a7 was refuted
   from our artifact (confirmed=false, sha 01f9c0f6, no w1 row).
2) Our fixes, each labs+suite gated and re-frozen in writing: squeeze
   self-cutoff guard (5c51cd9 — g02 replay proved our own walls raised
   bfs(cop,thief) to 16, minimax "fled" = correct detour); graded SURVIVAL
   leaves COP-ONLY + 18s budget (2915e7a — flat leaves made beyond-horizon
   argmax first-legal-move; golden case 9 re-pinned N->S, its own d3/d4
   pins disagreed = tie-break noise); agreement_poll_sec 120->10 (their
   instant seal + signed 30s turn clock vs our slow re-dial cadence).
3) Their fix: ARM-FIRST choreography (their standing shell owned sg1's
   first session; they arm and dial at our closed doors, we bounce once).
4) Attempt 4 (00:24-00:27): 6/6 verified, 47-47, uid 06f81d92 (unlabeled by
   written agreement), mutual sha 3601bd73 confirmed both engines. Report
   id 1a02b5f8c431cfb2 (league address only). Rule 35 CLOSED: their id
   1a02b655d0cba1cb, sealed copy byte-reconciled (file sha bdfb2601).
   Commits played: cop 2915e7a / thief a17af03 vs their b8508a86c211/a7d3a5b4.
   Evidence + tag game_vs_cosmos77 + backup-20260823-cosmos77-counted.

Submission freeze (same night):
- Cop default chain corridor -> PLAIN (3ade416): re-measured post-fixes,
  plain dominates/ties corridor on every corridor_lab row and beat it live.
- Submission builder bug FOUND BY OPERATOR on the built form: drawn series
  filed as losses (series_tie read from the ledger row where it never
  existed). Fixed both repos (cop rows.py 14fc4e9, thief ledger.py 4eb34a3
  — thief has its own module; first sync commit was dead code, corrected).
  Form now 7W/1L/2D, 759 points, 10 legal games.
- CI was RED since 08-22 13:29 (both repos): two replay-viewer tests
  assumed a populated results/ dir (fresh-clone unsafe) + one ruff-format
  nit. Fixed (cop bab0186, thief 152909a).
- v1.0-submission re-created ANNOTATED (Appendix C requires -a; the -f
  re-points had degraded it to lightweight) at final HEADs, both repos.
- Coverage cop 97.29% / thief 96.95% (gate 94). Suites 1997/1301 green.
- PDF vibecode-ex07 rebuilt and uploaded to Moodle by operator.
