# Cop RL + Search Research Report — chebyshev/minimax program

Date: 2026-08-10
Status: **SHIPPED** — this is the engine that played and won the counted series
vs `imreeyal` (90–30, 6/6 audits Verified OK, 2026-08-10 21:25).

> **Course requirement note.** The arena matrix, adversarial-archetype sweep,
> fixed-start A/B, and evaluation-weight study in this report constitute the
> project's **sensitivity analysis / parameter-variation** evidence: the same
> engine is measured while varying opponent style, search depth, training start
> distribution, and evaluation weights, with every variation traced to a
> promotion or rejection decision.

Supersedes: [`RL_RESEARCH_REPORT_20260809.md`](RL_RESEARCH_REPORT_20260809.md)
remains the record of the **book-model line** (`multiplicative_book_v1` scent,
population-oracle distilled champion). That line was superseded on 2026-08-09/10
when Step-0 negotiation with `imreeyal` locked `subtractive_chebyshev_v1` and
the whole movement stack was rebuilt for the new physics.

## 1. Motivation — the Step-0 scent negotiation

The scent model is a signed Step-0 term. Our previous champions were trained on
the book field (`multiplicative_book_v1`, clamped). The `imreeyal` pairing
proposed `subtractive_chebyshev_v1`; the user-approved decision (recorded in
`docs/CLAUDE_SCORE100_EXECPLAN.md`, 2026-08-09/10 entry) was to **accept** it
and rebuild, rather than refuse. The cost of playing the old nets under the new
field was measured, not guessed: on the honest harness (below) the superseded
book cop scores **0.2148** under chebyshev — unusable.

## 2. The position-oracle discovery

Under `subtractive_chebyshev_v1`, the transmitted frame's **unique 0.8 peak is
the emitter's current cell**: frames merge by max and then decay subtractively,
so every older peak is ≤ 0.7. Both sides are therefore effectively **sighted**.
Hiding is information-theoretically impossible; the game becomes geometry.

This turned the serving problem from a POMDP into deterministic pursuit, and
motivated a search engine instead of a learned policy for sighted frames:

- `cop_worker/rl/chebyshev_tracker.py` — exact opponent-cell extraction;
- `cop_worker/rl/pursuit_search.py` — depth-limited minimax with a
  territory-based evaluation, region-shrinking barrier heuristic, and the
  rule-46 place-onto-thief endgame;
- `cop_worker/rl/search_policy.py` — the `hybrid_search` adapter behind
  `[protocol] move_policy`: **minimax plays sighted frames; the RL net moves
  only on blind/ambiguous frames**.

Design decisions AD-2..AD-4, AD-6 in `docs/DESIGN.md`; per-algorithm PRD in
`docs/PRD_search_engine.md`.

## 3. From-scratch chebyshev training (2026-08-10 overnight)

Recipe: RecurrentA2C-GRU (v2 recipe base), env
`COPTHIEF_UNIFORM_BELIEF=1 COPTHIEF_SCENT_MODEL=chebyshev`, 12 generations per
role at ~2–3 min/generation, alternating frozen cross-generation opponents
(driver logs in `rl_experiments_20260810/`, workspace root).

**Regression finding (the negative result worth keeping).** On the in-run quick
eval, the cop's *resumed* generations regressed **monotonically**: gen01 0.933
falling to gen09 0.32. Resuming a cop checkpoint against a shifting frozen
opponent ladder degraded it every generation; the first fresh-seed generation
was the best cop of the run. The thief did not show this: it plateaus at ~0.85
around gen03–05. Consequence: wave-2 training used independent fresh seeds, and
promotion was decided only on the honest harness below, never on the in-run
numbers.

**Honest harness** (`scripts/eval_candidate.py`, fixed configured starts,
seed 20260810, 30 games/family, `scent=chebyshev` / `belief=prod`):

| Candidate | Win rate | Superseded book champion, same field |
|---|---:|---:|
| cop gen01 (random-start recipe) | **0.8704** | 0.2148 |
| thief gen05 (thief repo) | **0.985** | 0.4185 |

Promoted 2026-08-10 as `cop_chebyshev_champion.pt` (commit 9a30680), then
superseded the same day by the fixed-start recipe (§4).

## 4. Fixed-start A/B — start-position sensitivity

Match starts are **signed terms** (`cop_start [0,0]`, `thief_start [3,3]`): a
counted match always opens there, so training may pin the opening
distribution. New `--fixed-start-fraction` in `train_recurrent`; A/B on the
fixed-start harness (30 games/family, seed 20260810):

| Role | Recipe | Win rate | Decision |
|---|---|---:|---|
| cop | fixed-start fraction 0.8 | **0.9926** | **promoted** (commit 1a5338f) |
| cop | fixed-start fraction 0.5 | 0.9889 | rejected |
| cop | random-start incumbent (gen01) | 0.8704 | superseded |
| thief | random-start incumbent | **0.9741** | **kept** |
| thief | fixed-start | 0.9444 | rejected |

The roles moved in **opposite directions**: pursuit benefits from memorizing
the signed opening; evasion benefits from start diversity. The promotion rule
was honored both ways — a recipe changes only if comparable-or-better on the
default-start eval.

## 5. Arena matrix — search vs RL (`scripts/arena_search_eval.py`)

Head-to-head under chebyshev physics with the reference-v3 round order
(thief moves first; each side sees the other's post-decay frame), rule-46/47
captures, jittered thief openings. This is the promotion evidence for
`hybrid_search`:

| Pairing | Result |
|---|---|
| search cop d3 vs best RL thieves (gen03/gen05) | **12/12 + 12/12 captures**, mean end step ~12 |
| best RL cop vs search thief d3 | **0/12 captures** (full survival) |
| search cop d3 vs search thief d3 | 12/12 captures |
| search cop d3 vs search thief **d4** | thief survives 6/6 |
| search cop **d4** vs search thief d4 | 4/4 captures, mean step 18, ~3 s/half-move |

Search dominates RL in both directions; depth matters at the search-vs-search
frontier (d4 cop breaks the d4 thief that survives a d3 cop). Serving depth is
therefore iterative-deepening 2..4 (§7).

## 6. Adversarial-archetype sweep (`scripts/arena_archetypes.py`)

Final pre-window sweep vs opponent styles not otherwise tested (commit
735406c; 6 games each, jittered starts, seed 20260810):

| Archetype opponent | vs our side | Result |
|---|---|---|
| WallCutter cop (mid-board wall, hunts the cut half) | our search thief d4 | **0/6 captures** — survives all 35 rounds |
| ClaimFork cop (greedy chase + adjacent rule-46 place) | our search thief d4 | **0/6 captures** — survives all 35 rounds |
| ParityDodger thief (max distance + opposite parity) | our search cop d4 | **6/6 captures** at ~step 15 — walls break parity |

The parity result is the interesting one: a bare chaser can never catch an
opposite-parity dodger on a grid, but the barrier budget changes the graph.

## 7. Depth/latency sensitivity

Raw depth-4 minimax measured up to **~74 s** on an open midgame (d3 → d4
measured 7.8 s → 67 s) against a 180 s live turn budget. Fix: **iterative
deepening 2..4 under a wall-clock budget, with a ~10x next-ply cost prediction**
— a depth is not started unless its predicted cost fits (a between-depths check
alone had let a 74 s depth-4 through). Post-fix worst observed ~**7 s**, typical
~**3 s** at depth 4; every live half-move stayed inside the 10 s budget.

## 8. Evaluation-weight sensitivity (distance vs territory)

The static evaluation is `-40·dist - 16·territory` (cop-positive), where
territory = cells the thief reaches **strictly first**. Both terms were
measured, not chosen:

- **Distance-dominant (60/8)**: the minimising thief *preferred a far corner*
  over the open centre (dist 6 / territory ~10 beat dist 3 / territory ~24) and
  ran itself into the greedy cop's perimeter sweep — **captured in 11 moves,
  live, 2026-08-10**. Rebalancing to **40/16** makes centre-with-escape-room win
  for the thief while the cop keeps strict approach and herding gradients.
- **Territory vs raw flood-fill**: a plain flood-fill region barely changes as
  the cop approaches, so a horizon-limited minimax saw every approach as futile
  and **camped** (observed live: cop parked at (4,4) for 20 turns while the
  thief sat in a corner). Strictly-first reachability shrinks under approach and
  only credits walls that cut real escape routes.

Full derivation in the `evaluate` docstring in `cop_worker/rl/pursuit_search.py`.

## 9. Live-found engine fixes (rehearsal iteration, commit e5b0116)

Four bugs no unit test saw, found by iterating the production sparring
rehearsal:

1. **Wire cells are [row, col]** (kit convention). We sent [x, y]: our barriers
   registered transposed in the peer's physics and off-diagonal captures could
   never settle. Conversion now happens only at the wire boundary
   (`_to_wire_cell`/`_from_wire_cell`); internal state stays [x, y].
2. **Rule 47 was unreachable in the search**: STAY is always "legal", so
   "no legal move" never fired and place-onto-the-last-exit forks were
   invisible. Enclosed now means *no non-STAY move*.
3. **Territory eval** replaced raw flood-fill (§8).
4. **The thief was blind all game**: it absorbed the cop's turn by exact step
   match, but the cop's newest turn is r−1 when the thief plays round r — so it
   ran on RL fallback only (identical rollouts across eval retunes gave it
   away). It now absorbs the cop's r−1 frame.

After the fixes, the full production rehearsal scored 6/6 audits Verified OK
(thief survives 3/3 windows, cop captures 3/3 at ~step 13).

## 10. Live validation

| Series (all reference-v3, production path) | Result |
|---|---|
| Sparring rehearsal (production config, real HTTP) | 6/6 audits OK; thief survival ×3, cop capture ×3 @ ~step 13 |
| Full simulated friendly (role-router shim, kit peer) | **90–30**, 6/6 audits OK; kit `check_artifacts` = ALL SETS AGREE |
| Friendly vs imreeyal, 2026-08-10 20:00 | **90–30**; survivals sg1/3/5, captures sg2 @14, sg4 @16, sg6 @16 |
| Friendly #2 vs imreeyal, 20:36 | **90–30**, first fully-autonomous settlement |
| **COUNTED vs imreeyal, 21:25** | **90–30**, 6/6 audits Verified OK; survivals g01/03/05, captures g02/04/06 |
| (baseline) COUNTED vs anrbj666, old book engine | **lost 35–75** |

The counted swing from 35–75 (book-model line) to 90–30 (this program) is the
end-to-end validation of every decision above.

## 11. Artifacts

| Item | Location |
|---|---|
| Shipped cop model | `models/cop_chebyshev_champion.pt` (manifest-selected; see `docs/RL_MODEL_CARD.md`) |
| Arena harness | `scripts/arena_search_eval.py` |
| Archetype harness | `scripts/arena_archetypes.py` |
| Honest eval harness | `scripts/eval_candidate.py` (+ `eval_policy_quality.py`) |
| Training generations + A/B checkpoints | workspace `rl_experiments_20260810/` (cop_gen01..12, ab_start/) |
| Running log with all raw numbers | workspace `docs/CLAUDE_SCORE100_EXECPLAN.md` |
| Counted evidence | `evidence/game_vs_imreeyal/` |
