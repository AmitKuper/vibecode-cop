# Recurrent policy reproduction — cop

The counted movement policy is `RecurrentA2C-GRU`, not the legacy PPO experiment stack.
`agent/rl/train_recurrent.py` trains and evaluates from `LocalObservation`, Bayesian
`BeliefState`, and recurrent history. It applies the legal-action mask before every
sample or argmax. Counted inference loads only the checksum-pinned manifest artifact.

## Frozen champion

- Artifact: `models/cop_recurrent_champion.pt`
- SHA-256: `1c6f85bed3ba754d1daa38aa394b455d605fe1768436532581cc118b5be96949`
- Training: 2,400 episodes / 84,000 maximum environment steps
- Seed: `20260805`
- Hidden size: 128; gamma: 0.99; initial learning rate: 3e-4
- Method: local-belief behavioral-cloning warm start followed by recurrent A2C
- Historical opponent: `models/thief_ppo_best.pt`, SHA-256
  `b1769c9e67ce571efa971a345e08a10d9c33a5710e6eb7ce0c8896a1b2feab5c`

## Exact held-out rerun

Run from this repository after `uv sync --frozen`:

```powershell
uv run python -m agent.rl.train_recurrent `
  --role cop `
  --eval-series-per-family 120 `
  --seed 20260805 `
  --historical-checkpoint models/thief_ppo_best.pt `
  --evaluate-only-artifact models/cop_recurrent_champion.pt `
  --evidence-dir reproduced-results
```

The deterministic fields must match `results/cop_held_out_tournament.json` exactly.
Wall-clock and inference-latency samples are measured afresh and therefore are not
byte-identical. `scripts/verify_100_readiness.py` performs this rerun and comparison.

## Training or continuation

Fresh training uses the same command without `--evaluate-only-artifact` and with
`--episodes`. A continuation additionally supplies `--resume-artifact` and the
resume hyperparameters. Training is CPU-capable; a GPU is optional. The resulting
artifact is not deployable until its hash, manifest schema, held-out result, and
paired promotion gate are updated together.
