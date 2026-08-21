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
