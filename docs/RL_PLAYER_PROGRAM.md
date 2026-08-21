# The learned-player program — algorithms at training time, weights at match time

Goal (operator decision, 2026-08-21): a smart player whose MATCH-TIME
decisions come from learned weights, built AlphaZero-style — the search
stack and exact solvers serve as teachers and sparring partners during
training only. Firewalled from production until promotion criteria are met.

## Phase 1 — full-stack distillation, both roles (DONE 2026-08-21/22 night)

Teachers = the complete production stacks: cop (minimax d4 + stall-squeeze)
and thief (minimax d4 + confined-mode LineEscape). Corpus: 550 cop episodes
(evader-heavy pool) + 400 thief episodes vs a cop pool of FOUR randomized
sweep cops per cycle (line position / orientation / sweep direction all
varied — partition-avoidance as a concept, not a memorized column), the
production stack cop with and without the hook, and a greedy chaser. The
thief teacher survived ALL 400 collection episodes — including vs our own
stall-squeeze cop.

Students: GRU (deployed arch) + memoryless MLP per role, class-weighted
behavior cloning, sighted regime (chebyshev + uniform belief).

| test | minimax-only | full stack | FF student | GRU student |
|---|---|---|---|---|
| cop arena 28 games (prev. night) | 20/28 | 22/28 | 22/28 | 22/28 |
| thief arena 14 games (joint) | 14/14 | 14/14 | 14/14 | 14/14 |
| **sequential sweep-cop acid test** | **capture @26** | survival | **survival** | **survival** |

Findings:

1. **The learned thief beats the strategy that beat us live** (yanell11's
   line-partition cop), from weights alone, in the sequential (wire-order)
   test where plain minimax at depth 4/6/8 all die at step 26.
2. **Harness honesty note**: the joint-action thief arena turned out to be
   non-discriminating (even minimax-only survives under simultaneous
   moves — the sweep kill needs the wire's thief-first sequencing). The
   discriminating instrument is `scripts/line_sweep_lab.py`; conclusions
   are drawn from it.
3. **Robustness signal**: students were trained on joint-convention
   transitions and evaluated sequentially — the behavior transferred.
4. Val accuracies: cop GRU 0.940 / FF 0.928; thief GRU 0.936 / FF 0.930.
   Memoryless matches recurrent in rollouts on both roles.

Repro: `collect.py --role cop|thief` (sharded) → `train.py --arch gru|ff
--role ...` → `arena.py` / `arena_thief.py` / the sequential labs.
Artifacts in results/barrier_distill/ (gitignored, local).

## Phase 1 extended — curriculum iterations and the interference frontier
## (2026-08-22, four rounds, all measured)

| thief student | corpus / teacher | legacy (champ 0.827) | sweep acid test |
|---|---|---|---|
| v1 | sweep-heavy, search teacher | 0.374 | **survives** |
| v2 | + classic families, search teacher | 0.527 | (untested) |
| v3 | mixture teachers (champion on families) | **0.798 ≈ parity** | captured @25 |
| v4 | filtered union of v1+v3 corpora | **0.802 ≈ parity** | captured @19 |

| cop student | corpus / teacher | legacy (champ 0.959) | arena (teacher 22/28) | seq. mirror2 |
|---|---|---|---|---|
| ff v2 | corridor corpus, search teacher | 0.667 | **23/28 > teacher** | **capture @8** |
| gru v3 | mixture teachers | 0.831 | 20/28 | — |
| gru v4 | filtered union | 0.770 | 18/28 | — |

Findings, in order of importance:

1. **Per-skill expert parity is fully achievable by distillation.** For every
   instrument there exists a student at or above the relevant expert:
   thief legacy 0.798-0.802 vs champion 0.827; thief sweep survival (v1);
   cop arena 23/28 vs teacher 22/28; cop sequential mirror2 @8.
2. **The teacher-quality diagnosis paid off**: the search stack is genuinely
   WEAKER than the RL champion against belief_pursuit (0.37 vs 0.78) and
   targeted_exploit (0.33 vs 0.78) — the families it trained on. Mixture-of-
   experts teaching (champion on its families, search on the new threats)
   lifted thief legacy 0.527 -> 0.798 in one round.
3. **The frontier is capability interference, not method**: no single
   128-hidden GRU holds ALL skills at once. The naive union corpus made the
   cop WORSE on both instruments (0.831 -> 0.770; 20 -> 18) — conflicting
   expert styles on overlapping states at fixed capacity.
4. Levers for closing the last gap, in expected order of value:
   **capacity** (256+ hidden), **DAgger** (on-policy relabeling by the
   per-state best expert), and **Phase 2 RL fine-tune** (reward arbitrates
   where imitation conflicts). All three are standard responses to exactly
   this failure mode.

Production stance unchanged: the search stack plays matches; no student is
promoted (the bar is "matches the incumbent on EVERY instrument", and no
single artifact does yet).

## Phase 2 — RL fine-tune from distilled weights (NEXT)

Initialize from the Phase 1 students; PPO/A2C against the hard pool
(search stacks, randomized sweep cops, exact evaders, frozen past
students) with solver-shaped wall rewards for the cop. Success = exceeding
the distilled baseline on any discriminating instrument without regressing
the others.

## Phase 3 — promotion (gated)

Full eval + peersim + manifest entries with honest obs_mode; serve with
`move_policy = "rl"` in FRIENDLIES first; hybrid_search stays the counted
default until the net matches it on every instrument. Known ceilings,
stated once: vs perfect play the game value is a draw (nobody beats it),
and a net cannot counter strategy classes absent from its training pool —
the adversary library grows with every opponent that shows us a new one.

## Phase 1 final state (2026-08-22 evening, rounds v5-v8)

Capacity (256 hidden) + two DAgger rounds + one targeted round, measured:

| artifact | legacy | new-threat instruments | verdict |
|---|---:|---|---|
| thief_gru_v7 | 0.802 (champ 0.827) | sweep SURVIVAL, arena 14/14 | **UNIFORM — done** |
| cop_gru_v7 | 0.897 (champ 0.959) | arena 21-22/28, both acid captures | best cop; 4-family gap |
| cop_gru_v8 (targeted) | 0.885 | arena 20/28 | traded families — DAgger plateau |

Conclusions: DAgger closed the thief completely (the sweep-weighted round
was decisive) and took the cop from 0.667 to ~0.90 with belief_pursuit
12/27 -> 27/27, but plateaus ~0.06 short of a champion that RL-specialized
on these exact families for 105k steps. The uniform cop's remaining path
is Phase 2: PPO fine-tune of cop_gru_v7 against the weak families with
reward arbitration — imitation cannot out-imitate a reward-optimized
specialist in its own niche. The thief side of "strongest in all
situations, from weights" is ACHIEVED and reproducible.
