# Cop RL Training Research Report

Date: 2026-08-09  
Authoritative `game.json` SHA-256:
`9d6ec544143d1e5768e70b64a3d28f101d9060ad46ad2de703947654ec5eb639`

## Outcome

The population-oracle distilled recurrent cop beat the checked-in recurrent
champion on the paired held-out suite while preserving the production recurrent
checkpoint schema.

| Cop policy | Wins | Win rate (Wilson 95%) | Official score | Worst family | p99 inference |
|---|---:|---:|---:|---:|---:|
| Incumbent RecurrentA2C-GRU | 902/1,200 | 75.17% (72.64–77.53%) | 19,530–7,490 | 0.0% | 4.02 ms |
| **Population-oracle distilled GRU** | **1,153/1,200** | **96.08% (94.83–97.04%)** | **23,295–6,235** | **71.67%** | **4.51 ms** |

This is a gain of 20.92 percentage points and, more importantly, removes the
incumbent's complete failure on its weakest opponent family. The candidate is
the best cop produced in this study and was subsequently wired as the
manifest-selected counted policy. The previous checkpoint remains available
for rollback.

Machine-readable tournament evidence:

- [`cop_incumbent.json`](../results/rl/research_20260809/cop_incumbent.json)
- [`cop_candidate.json`](../results/rl/research_20260809/cop_candidate.json)

No rollback model, protocol file, game physics, or `game.json` was overwritten.
The model manifest was intentionally updated during the later wiring step.

## Rules and information boundary

Training and evaluation used the current `game.json` parameters: a 7×7 board,
cop start `[0,0]`, thief start `[3,3]`, simultaneous `N/S/E/W/STAY` movement,
14 cop barriers, a 35-turn survival threshold, and six gamelets per series.
Capture scores are 20/5 for cop/thief; survival scores are 5/10. Scent uses the
configured 5×5 radial field with 0.9 center intensity and 0.9 temporal
retention.

The canonical transition order was unchanged: barrier placement, immediate
barrier-on-thief capture, cop move, thief move, overlap capture, turn-35
survival, and trapped-thief capture. Policies receive only the public state,
their own position, opponent scent, and Bayesian opponent-position belief. The
research policies use the same 201-element local feature vector as production;
belief-search rollouts never receive the true hidden thief coordinate.

## Baseline audit

The existing tournament JSON was not a reliable champion baseline. The old
evaluator randomized starts despite fixed configured starts, reset recurrent
opponent state on every decision, forced the historical thief to argmax instead
of its manifest temperature, and supplied `turn % 6` as the gamelet feature.
The corrected evaluator retains recurrent state, uses the configured starts,
and holds one gamelet number constant for the game. Corrected fixed-start
cross-play showed the incumbent thief winning 29/30, revealing a materially
harder cop training target.

## Cop experiments

The full two-role study completed 25,500 training/teacher games, 554,356 DDQN
environment steps, and more than 10,000 evaluation games. Cop-specific results
were:

| Experiment | Scale | Result |
|---|---:|---|
| Corrected incumbent cross-play | 30 fixed + 120 random | Fixed: cop 1/30; random: cop 52/120. Established start sensitivity. |
| Greedy-logit hybrid sweep | 14 role/config combinations | Small pilot gains, but brittle worst-family behavior. |
| Belief depth-search hybrid | Depths 1–2 plus strength/particle sweep | Useful diagnostic; search alone did not beat the final learned policy. Optimized p99 was 28.4 ms. |
| Tabular Q-learning | 500 episodes | 0% against the incumbent thief; state aliasing prevented generalization. |
| Legacy PPO/DQN artifacts | Representative checkpoint sweep | Best legacy PPO only tied the current opponent on score in a 12-game pilot. |
| Dueling Double-DQN pilot | 500 episodes | 30% fixed head-to-head; promising but not competitive. |
| Dueling Double-DQN scale-up | 3,000 episodes | 98.3% versus the incumbent thief but only 68.3% family aggregate. |
| Recurrent A2C continuation | 300 episodes | 1/30 versus incumbent thief; no improvement. |
| Anti-loop scripted teacher | Local belief/scent policy | 30/30 versus incumbent thief, exposing a large strategy ceiling. |
| Single-teacher sequence distillation | 300 teacher games, 100 updates | 119/120 target wins, but wall-family and randomized-start regressions. |
| **Population-oracle distillation** | **600 teacher games, 200 updates** | **118/120 target, 97.5% pilot family rate, 83.3% pilot worst family. Selected.** |
| Rehearsal distillation | 1,000 games, 300 updates | Improved random robustness but slightly reduced fixed/family performance. |
| PSRO round-4 cop response | 4,000 DDQN episodes, 135,622 steps | Failed against the new thief counter: 1/6 captures and 28.3% family aggregate. |

## Why the selected method worked

The successful cop was trained by supervised sequence distillation from a
teacher chosen from a frozen opponent/strategy population. This combined the
strong local anti-loop pursuit logic with a production-compatible recurrent
policy. Training against a frozen population avoided the moving-target failure
of simultaneous self-play and exposed non-transitive counters before a model
was called a champion.

Future rounds should retain the incumbent, the new recurrent cop, scripted
families, and learned thief counters in the opponent pool. A response should be
added only after population-wide evaluation, not replace the prior policy based
on one head-to-head result.

The approach follows the motivation behind Double Q-learning, recurrent RL for
partial observations, fictitious self-play, PSRO, and belief-space planning:
[van Hasselt et al.](https://ojs.aaai.org/index.php/AAAI/article/view/10295),
[Hausknecht and Stone](https://arxiv.org/abs/1507.06527),
[Heinrich and Silver](https://arxiv.org/abs/1603.01121),
[Lanctot et al.](https://arxiv.org/abs/1711.00832), and
[Silver and Veness](https://papers.nips.cc/paper/2010/file/edfbe1afcf9246bb0d40eb4d8027d90f-Paper.pdf).
The implemented search is a small belief-weighted determinized simultaneous
search, not an exact POMDP solver.

## Candidate artifact and loading

| Purpose | Workspace artifact | SHA-256 |
|---|---|---|
| Selected deployable cop | `rl_experiments_20260809/distill/cop_population_oracle_600/cop_recurrent_candidate.pt` | `9c5aee7f5b80f29a539c6124fd73f129cb6bef8f4a63f27ae4b12c4a8b09c73e` |
| Incumbent cop | `models/cop_recurrent_champion.pt` | `e57f068e88fea557be1130d0c15c8783b1eecfc2c693ddad4582a1c250516d7c` |

The candidate uses the same recurrent dictionary schema as production:

```python
checkpoint = torch.load(path, map_location="cpu", weights_only=True)
network = RecurrentActorCritic(
    checkpoint["input_size"],
    checkpoint["n_actions"],
    checkpoint["hidden_size"],
)
network.load_state_dict(checkpoint["state_dict"])
network.eval()
```

Production loading validates role, algorithm, observation/action and belief
schemas, plus the published SHA-256. The selected artifact is installed as
`models/cop_population_oracle_champion.pt`; it does not overwrite the rollback
checkpoint.

## Verification and recommendation

- The final comparison uses identical seed namespaces, fixed configured starts,
  10 opponent families, 20 six-gamelet series per family, and 1,200 games per
  policy.
- New research code passes Ruff and all 75 relevant transition, scent, belief,
  action-mask, recurrent-loader, environment, and research tests.
- Full cop suite: 1,345 passed and 1 skipped.
- The information-boundary test produces identical search scores when only the
  real hidden thief coordinate changes while the cop belief remains fixed.

The distilled recurrent candidate is now selected by the checksummed manifest.
Run a real networked six-gamelet series before external use. For future
training, bootstrap confidence intervals over whole series
and train recurrent Dueling Double-DQN with sequence replay as a complementary
population member rather than replacing the successful distilled policy.
