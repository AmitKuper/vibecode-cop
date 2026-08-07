# Recurrent policy reproduction — cop

The counted policy is `RecurrentA2C-GRU`. It consumes `LocalObservation`, Bayesian
`BeliefState`, and recurrent history, then applies the legal mask and canonical
domain validation. The heuristic is a training opponent and development fallback,
not a counted fallback.

## Frozen champion

- Artifact: `models/cop_recurrent_champion.pt`
- SHA-256: `b9e74b7a13ca461484f2b47046eeecf8d393cb8d64b7cdd51d2915b714c21268`
- Training-code SHA: `e052b799e1f732cd140fe3b51af6165566c239c9`
- 11,800 cumulative episodes / 413,000 maximum environment steps
- Seed 20260805; hidden size 128; gamma 0.99; final learning rate 1e-5
- Method: local-belief BC warm start, recurrent A2C, adversarial curriculum, and
  belief-supported trap shaping
- Historical thief SHA-256:
  `b1769c9e67ce571efa971a345e08a10d9c33a5710e6eb7ce0c8896a1b2feab5c`

## Exact held-out rerun

After `uv sync --frozen`:

```powershell
uv run python -m cop_worker.rl.train_recurrent `
  --role cop --episodes 0 --eval-series-per-family 30 `
  --seed 20260805 --hidden-size 128 `
  --historical-checkpoint models/thief_ppo_best.pt `
  --evaluate-only-artifact models/cop_recurrent_champion.pt `
  --evidence-dir reproduced-results
```

Artifact SHA, counts, wins, official scores, per-family outcomes, and promotion fields
must match `results/cop_held_out_tournament.json`. Timing fields are measured afresh.
Any newly trained artifact remains undeployable until the checksum, manifest,
held-out report, and paired promotion gate are updated atomically.
