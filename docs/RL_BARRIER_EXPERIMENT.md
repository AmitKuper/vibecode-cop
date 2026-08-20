# Can a net learn the barrier strategy? — distillation experiment, 2026-08-21

One-night research experiment (`scripts/barrier_distill/`), fully firewalled
from production: no MANIFEST, champion, or serving-path change; checkpoints
and shards live in the gitignored `results/barrier_distill/`.

## Question

The cop's barrier play is algorithmic: minimax (depth 4) for tactical walls
plus the stall-squeeze hook (exact survival tables) for strategic ones
(`docs/ANTI_EVADER_ANALYSIS.md`). Can a neural policy learn that behavior
from demonstrations, in the sighted (chebyshev) regime where barriers
actually matter — and does it need memory to learn the *timing* (the hook
fires on a 4-turn stall pattern, which is history, not state)?

## Setup

- **Teacher**: the production sighted stack exactly (`StallSqueeze` override,
  then `best_cop_action` d4) on true positions — privileged teacher, blind
  student.
- **Observations**: the production 201-dim tensor via the standard training
  pipeline under `COPTHIEF_SCENT_MODEL=chebyshev` +
  `COPTHIEF_UNIFORM_BELIEF=1` (what a sighted counted game actually feeds).
- **Data**: 550 episodes (10 parallel shards × 55), thief pool weighted
  toward the wall-myopic exact-evader class (8/11 of each cycle) plus our
  minimax thief and two scripted thieves; joint-action canonical domain
  physics. 327 PLACE labels (~4–5% of steps) → class-weighted cross-entropy
  (√inverse-frequency, capped ×20).
- **Students**: `gru` = the deployed `RecurrentActorCritic` (has memory);
  `ff` = an equal-budget memoryless MLP (the ablation).
- **Arena**: 7 opponents × 4 starts, same physics and observation pipeline
  for students and search baselines alike.

## Results

Imitation metrics (held-out episodes): GRU val accuracy 0.940, PLACE recall
0.91 / precision 0.91; FF val accuracy 0.928, PLACE recall 0.91 /
precision 0.76.

Arena (cop wins /4 per opponent; `w` = walls placed across the 4 games):

| opponent          | minimax | hook (teacher) | ff student | gru student |
|-------------------|--------:|---------------:|-----------:|------------:|
| evader: mobility  | 0/4 w0  | 2/4 w5         | 2/4 w5     | 2/4 w4      |
| evader: distance  | 4/4 w4  | 4/4 w4         | 4/4 w4     | 4/4 w4      |
| evader: center    | 4/4 w0  | 4/4 w0         | 4/4 w0     | 4/4 w0      |
| evader: mirror2   | 4/4 w0  | 4/4 w0         | 4/4 w0     | 4/4 w0      |
| minimax thief d3  | 0/4 w0  | 0/4 w0         | 0/4 w1     | 0/4 w2      |
| scripted: away    | 4/4 w4  | 4/4 w4         | 4/4 w4     | 4/4 w4      |
| scripted: random  | 4/4 w1  | 4/4 w3         | 4/4 w0     | 4/4 w1      |
| **total**         | **20/28** | **22/28**    | **22/28**  | **22/28**   |

## Findings

1. **Yes — the barrier behavior is learnable by imitation.** Both students
   reproduce the teacher's arena score exactly (22/28), including the two
   behaviors that matter: placing 1–2 walls against the evader variants that
   require them, and *restraint* — zero walls where pure pursuit already
   wins. The plain-minimax column (20/28, 0/4 vs the mobility evader)
   confirms the wall behavior is what they learned, not just chasing.
2. **The memory hypothesis was wrong.** The memoryless MLP matches the GRU
   in rollouts (the GRU is cleaner on label precision only). The 201-dim
   observation — barriers-placed channel, step scalar, scent peak —
   evidently identifies wall states without needing to count stall turns.
3. **The imitation ceiling is real.** No student beats the teacher anywhere,
   and *everyone* — teacher included — loses 0/4 to our own minimax thief,
   which anticipates future walls (consistent with the exact-solve result
   that the draw is the value of the game against wall-aware defense).
4. **Speed is the one student advantage**: ~1 ms/move vs ~1–2 s/move for the
   search stack — irrelevant here (turn budget 180 s), decisive only if the
   game were much larger.

## Production recommendation

Keep the search stack in production; do not promote a student. The student
matches but never exceeds the teacher, carries no guarantees (the hook's
never-preempt-a-capture / strict-improvement / no-self-trap properties are
proven, a net's are not), and the counted league is one-shot. The experiment
stands as evidence for the report: the team measured *when learning is the
right tool* — imitation reproduces computed strategy at 1000× less per-move
compute, and exact computation stays ahead where it is feasible.

Repro: `collect.py` (10 shards) → `train.py --arch gru|ff` → `arena.py
--policy minimax|hook|<ckpt>`; arena JSONs land beside the checkpoints.
