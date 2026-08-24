# PRD — search engine (`hybrid_search`)

Per-algorithm PRD for the serving move engine: exact opponent tracking +
depth-limited minimax with territory evaluation, RL fallback for blind frames.
Code: `cop_worker/rl/chebyshev_tracker.py`, `cop_worker/rl/pursuit_search.py`,
`cop_worker/rl/search_policy.py`. Decisions AD-2..AD-4, AD-6 in `docs/DESIGN.md`.

## 1. Theoretical background

### Pursuit-evasion on grids

The game is a discrete pursuit-evasion (cops-and-robbers) game on the 7x7 grid
graph, with three domain twists: rounds are thief-move-then-cop-move, the cop may
spend a move placing one of 14 barriers, and capture also settles by rule 46
(barrier placed onto the thief's cell) or rule 47 (thief enclosed — STAY does not
rescue). In classic cops-and-robbers, cop-win graphs are exactly the
dismantlable graphs (Nowakowski–Winkler; Quilliot); a grid contains isometric
4-cycles and is not dismantlable, so a lone cop on the bare 7x7 grid cannot
corner an optimal evader. The barrier budget is what restores a cop win: walls
monotonically shrink the thief's usable region, which is why the evaluation
credits territory cuts rather than proximity alone, and why a barrier is worth
its forfeited move.

### The position oracle (chebyshev 0.8-peak, proof sketch)

Under `subtractive_chebyshev_v1` each turn emits a 5x5 chebyshev kernel
(centre 0.9, falloff 0.9/3 = 0.3 per ring), merges into the standing trail by
max, then everything decays by 0.1 (deposit-then-decay). Hence on the
transmitted frame:

- the freshly emitted centre reads 0.9 − 0.1 = **0.8**;
- its ring-1 neighbours read at most 0.6 − 0.1 = 0.5 from this emission;
- any cell last emitted k >= 1 turns ago has decayed at least one extra step,
  so it reads at most 0.9 − 2(0.1) = **0.7**.

The frame's argmax is therefore uniquely the emitter's current cell — the scent
field is a position oracle, not a probability cloud. A peer using the league's
other reading of the locked doc (fresh-deposit, 0.9 peak) yields the same
argmax; `exact_opponent_cell` accepts both conventions and returns `None` on
empty, tied or off-convention frames (the fallback path).

### Search

Both roles share one game tree with cop-positive values: the thief minimises
(`_round_value`), the cop maximises (`_cop_reply`), with alpha-beta pruning.
Terminals: co-location, rule 46, rule 47 (worth `CAPTURE + steps_left` — earlier
captures dominate) and step exhaustion (`SURVIVAL`). Leaf evaluation:

```
value = -40·bfs_distance(cop, thief) - 16·territory(thief) + 2·(35 - steps_left)
```

where **territory** = cells the thief reaches strictly before the cop (two BFS
distance maps). A plain flood-fill region barely changes as the cop approaches,
so a horizon-limited search saw all approaches as futile and camped (observed
live); territory strictly shrinks under approach and only credits walls that cut
real escape routes. The 40/16 weights are empirical (see `evaluate` docstring):
distance-heavy weights drove the minimising thief into corners.

Depth is iterative deepening 2..4 under a wall-clock budget, and a depth is not
started unless the predicted ~10x cost of the next ply fits (measured d3 → d4:
7.8 s → 67 s; a between-depths check alone let a 74 s depth-4 through).

## 2. Requirements

- **Latency**: bounded per half-move by the iterative-deepening budget in
  `best_*_action` — cop 18 s (raised from 10 s on 2026-08-23, inside the signed
  30 s turn deadline), thief 10 s; worst observed live ~7 s, typical ~3 s at
  depth 4.
- **Correctness**: never emit an illegal move — the adapter checks the chosen
  action against the canonical domain's `legal_actions` and falls back otherwise.
- **Fallback discipline**: blind/ambiguous frame → last-known cell, else the
  manifest-pinned RL champion, else STAY. Hints are never read (movement is
  provably hint-independent — `docs/PROMPTS.md` §4).
- **Role symmetry**: one search serves both roles; the thief's root models the
  cop's remaining wall budget (under-counting hides enclosure danger).

## 3. Alternatives considered

- **Pure RL serving** — measured strictly weaker once frames are an oracle:
  search cop d3 vs best RL thieves 12/12 + 12/12 captures; best RL cop vs
  search thief 0/12 (`scripts/arena_search_eval.py`, jittered starts).
- **POMCP / belief-space planning** — unnecessary: the oracle removes partial
  observability on well-formed frames, and at 49 cells the exact minimax is
  cheap; POMDP machinery would buy nothing on sighted frames and the RL
  fallback already covers blind ones.
- **From-scratch retraining recipes (fallback nets)** — fixed-start A/B on the
  promotion harness: cop fixed-start(0.8) **0.9926** vs random-start 0.8704
  (starts are signed terms, so fixed-start matches deployment); the thief showed
  the reverse (random-start 0.9741 > fixed-start 0.9444) and kept its recipe.

## 4. Success indicators

| Indicator | Evidence |
|---|---|
| Arena matrix vs RL | search cop 12/12 (x2 thief families); RL cop 0/12 vs search thief |
| Search-vs-search sanity | cop d3 beats thief d3 12/12; cop d4 beats thief d4 4/4 (mean step 18, ~3 s/half-move) |
| Live friendly vs imreeyal | won 90–30, captures at steps 14/16/16, survivals x3 |
| Live counted record with this engine | 7W–1L–2D over ten series (`results/counted_series.json`), 6/6 audits Verified OK every series |
| Latency | every live half-move inside the per-role budget (cop 18 s / thief 10 s) |

## 5. Test scenarios (`tests/test_pursuit_search.py`)

- **TestTracker**: fresh-frame argmax is the emitter cell; trail history never
  steals the peak; 0.9 fresh-deposit convention resolves too; empty/tied/
  off-convention frames return `None`.
- **TestCopSearch**: steps onto the thief for the co-location capture; places
  onto the thief (rule 46) when stepping is unavailable.
- **TestThiefSearch**: evasion and enclosure awareness (rule 47 — STAY does not
  rescue; forks are visible).
- **TestServingAdapter**: falls back to the wrapped RL policy on blind frames;
  legal-action guard; reset clears the last-known cell.
- Live-fidelity regression pins: wire cells `[row, col]` conversion and
  per-sub-game policy reset (`tests/test_serving_episode_reset.py`).
