# Anti-evader analysis — why 47-47 happened and what the cop does about it

Date: 2026-08-20, after the counted draw vs SMNGRP05 (all six sub-games
survival; our cop 0/3 captures against their exact-induction thief).

## Ground truth (exact backward induction, this repo's rules)

Solver: value iteration over (cop, thief) with thief-first half-moves, STAY,
capture on co-location, rule-46 wall-drop, rule-47 immobilization — the same
semantics the wire plays.

1. **Open 7x7 is thief-win from every start, forever.** With no barriers, an
   optimal thief evades any cop movement policy indefinitely (checked to 200
   steps; the win set is empty at every horizon). Every 90-30 we scored came
   from opponents fielding sub-optimal thieves. SMNGRP05's thief was the
   first optimal one; 47-47 was the true value of barrier-less play.
2. **Every open rectangle down to 2x2 is thief-win**; only 1-wide corridors
   (trees) are cop-win. A winning plan must corner the thief in a
   tree-shaped region — walls are mandatory, and structure matters.
3. **Restricted-geometry exact solves found no forced capture from the real
   start within 35 steps** (double lines rows 2+4 / 4+5 / 1+3 / 3+5, column
   pairs, cross, comb, corner-box; each solved exactly over
   49x49x2^14 states, horizons to 60). Wins exist deep in each geometry's
   state space, but perfect defense never lets the game reach them. Against
   a perfect thief the draw appears to be the value of the game; we have not
   found (and doubt) a 35-step winning wall strategy.

## The exploitable class: exact-but-myopic evaders

An evader that re-solves the survival game on the CURRENT walls (SMNGRP05's
"exact backward induction over the joint state") is perfect only until the
first wall lands: it never avoids wall-enabling positions because its model
contains no future placements. One well-chosen wall flips its table and its
"safe" cells become traps.

## The fix: `cop_worker/rl/stall_squeeze.py`

`StallSqueeze.override` runs before minimax in `SearchRolePolicy` (cop only):

- **Trigger**: 4 consecutive turns at stable distance <= 4 — the provable
  minimax stall (an oscillating chase that theory says never captures).
- **Action**: among adjacent legal placements, the wall minimizing the
  thief's exactly-solved surviving-move count; strict improvement required;
  never walls the cop below 2 exits; at most 8 hook walls per sub-game;
  state reset per sub-game via `policy.reset()`.

## Verification round 2 (2026-08-20, same day) — bugs found and fixed

Re-review before committing found two defects the first tests missed:

1. **Direction-name rotation (game-losing).** The hook's hand-typed
   delta→name map disagreed with the production convention
   (`action_space.PLACE_DIRS`: `PLACE_N == (0, -1)`): it scored the right
   wall cell but returned the 90°-rotated action name, so on the wire every
   hook wall would have landed on the wrong cell — voiding the
   strict-improvement and self-trap guards. Fixed by deriving `_PLACE` from
   `PLACE_DIRS`; pinned by a test asserting the exact direction (`PLACE_S`
   for the between-cell in the SMNGRP05 mirror state), not just the prefix.
2. **Capture preemption.** The hook could fire at Manhattan distance 1,
   where minimax has capture-in-hand (step onto the thief, or rule-46 place
   onto its cell). Exact evaders never step there; weak thieves can. Added a
   `d <= 1` never-fire guard + test.

The matrix is now reproducible from the repo alone:
`python scripts/anti_evader_lab.py` drives the production `StallSqueeze` +
`best_cop_action` (depth 4) and applies actions with production deltas, so a
convention bug shows up as a lost match. Result with the fixed hook
(tie-breaks re-derived in the script; they differ in detail from the
original scratch run, so per-variant rows moved, but the qualitative claims
hold):

| variant  | plain minimax | with stall-squeeze |
|----------|---------------|--------------------|
| mobility | survival      | capture @ 10 (1 hook wall) |
| distance | capture @ 12  | capture @ 12 (hook silent) |
| center   | capture @ 6   | capture @ 6 (hook silent)  |
| mirror2  | capture @ 9   | capture @ 15 (2 hook walls) |

Known trade-off: the stall trigger is a heuristic (4 stable-distance turns),
not a proof of no-win, so it can fire during a slow convergence and delay a
capture (`mirror2`: 9 → 15). It has never flipped a capture into a survival
in any lab run — the sub-game outcome floor holds — and against true
evaders it is the only thing that converts draws into wins.

## Strength-guard verdict

No observation, scent, belief, mask, manifest, or thief-path change. The
hook fires only in stall states and never at capture-in-hand distance, so
its outcome floor is the old result (survival) and its ceiling is a new
capture; the one observed cost is a slower capture against one lab variant.
Suite 1950 passed / 4 skipped before the round-2 fixes; re-run green after
(stall-squeeze file 10/10). Sparring self-test 6/6 required before arming.
