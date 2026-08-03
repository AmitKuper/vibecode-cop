# RL Reproduction Guide

## Training Code Location

All RL training infrastructure lives in `agent/rl/`:

```
agent/rl/
  ppo.py           — PPO algorithm implementation
  ppo_update.py    — gradient update step
  rollout.py       — trajectory collection
  replay_buffer.py — experience replay
  trainer.py       — training loop coordinator
  league.py        — league/tournament manager
  cross_train.py   — cross-agent training utility
  evaluate.py      — checkpoint evaluation
  eval_compare.py  — side-by-side policy comparison
```

## Hyperparameter Space (from docs/RL_MODEL_CARD.md)

| Parameter         | Value       |
|-------------------|-------------|
| Algorithm         | PPO         |
| Learning rate     | 3e-4        |
| Clip epsilon      | 0.2         |
| GAE lambda        | 0.95        |
| Discount gamma    | 0.99        |
| Entropy coeff     | 0.01        |
| Value coeff       | 0.5         |
| Max grad norm     | 0.5         |
| Rollout steps     | 2048        |
| Mini-batch size   | 64          |
| PPO epochs        | 10          |
| Observation space | own pos (one-hot) + barriers + opponent scent + belief heatmap |
| Action space      | N/S/E/W/STAY/PLACE_N/PLACE_S/PLACE_E/PLACE_W (cop) |

## Reproducing Training

```bash
# EXTERNAL_PENDING — script not yet implemented
uv run python scripts/train_rl.py --role cop --episodes 1000000
```

Requires GPU with >=8 GB VRAM. Expected training time: ~12 hours on A100.

## Model Loading

```python
from agent.rl.policy_loader import load_manifest

policy = load_manifest("models/MANIFEST.json")
```

The manifest pins the checkpoint path, observation-space shape, and action-space
size. Shape mismatch raises `ModelCompatibilityError` at load time.

## Tournament Evaluation

```bash
# EXTERNAL_PENDING — script not yet implemented
uv run python scripts/run_tournament.py --n-games 100
```

Tournament results are appended to `docs/RL_TOURNAMENT_REPORT.md`.

## Current Status

- PPO infrastructure: complete
- Trained checkpoint: EXTERNAL_PENDING (requires GPU training run)
- Self-play curriculum: planned, not implemented
