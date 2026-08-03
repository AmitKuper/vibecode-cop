# RL Tournament Report

## Status: EXTERNAL_PENDING

Real training must complete before tournament results are valid.
Current results are all zeros (placeholder model).

## Tournament Architecture

Agents compete in round-robin against a population of opponents:
- **random**: Uniform random legal actions
- **heuristic_pursuit** (cop): BFS toward belief centroid
- **heuristic_evasion** (thief): Manhattan distance maximization from belief centroid
- **self_play**: Previous checkpoint versions

## Evaluation Protocol
- 100 episodes per matchup
- 6 gamelets per episode
- Win condition: cop catches thief within turn limit
- Metrics: win_rate, survival_rate, mean_turns, score_differential

## Promotion Criteria
A model is promoted to counted-mode when:
- `cop_win_rate > 0.55` vs heuristic_pursuit
- `thief_survival_rate > 0.55` vs heuristic_pursuit
- All schema version checks pass
- SHA-256 hash verified against MANIFEST.json

## Placeholder Results
All metrics are 0.0 — training required.
See `results/rl/tournament_results.csv` for current (placeholder) scores.

## Population-Based Training (Future)
Once baseline training completes, league play will cycle through:
1. PPO self-play warmup
2. Population expansion with heuristic opponents
3. ELO-ranked promotion ladder
