# Counted RL policy reproduction — cop

The selected counted policy is a population-oracle distilled
`RecurrentA2C-GRU`. It consumes `LocalObservation`, Bayesian `BeliefState`, and
recurrent history, then applies deterministic argmax through the canonical
legal-action mask.

## Frozen champion

- Artifact: `models/cop_population_oracle_champion.pt`
- SHA-256: `9c5aee7f5b80f29a539c6124fd73f129cb6bef8f4a63f27ae4b12c4a8b09c73e`
- Training-code Git blob SHA: `13090edb2245b5280e8affa758df5b4bf51360c3`
- 492,264 cumulative steps; hidden size 128; seed 20260809
- 600 teacher games, 9,264 examples, and 200 sequence-distillation updates
- Method: frozen population oracle followed by recurrent sequence distillation

## Loading and smoke test

After `uv sync --frozen`:

```powershell
uv run python -c "from cop_worker.rl.recurrent_policy import load_recurrent_policy; p=load_recurrent_policy('models/MANIFEST.json','cop'); print(type(p).__name__, p.inference_mode)"
```

The command must print `RecurrentRolePolicy argmax`. The loader recomputes the
artifact SHA-256 before reconstructing the network.

## Evidence

The paired 1,200-game incumbent and candidate tournament JSON files are in
`results/rl/research_20260809/`. Training commands, population composition,
limitations, and experiment results are recorded in
`docs/RL_RESEARCH_REPORT_20260809.md`.

Any future candidate remains undeployable until its artifact, checksum,
manifest metadata, held-out evidence, and model card are updated together.
