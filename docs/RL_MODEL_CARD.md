# RL policy model card — cop

Status: **DEPLOYED / LOCAL RESEARCH GATE PASS**. External league play remains
`EXTERNAL_PENDING`.

## Identity and intended use

- Role: cop; grid: 7×7; algorithm: population-oracle distilled
  `RecurrentA2C-GRU`.
- Artifact: `models/cop_population_oracle_champion.pt`.
- SHA-256: `9c5aee7f5b80f29a539c6124fd73f129cb6bef8f4a63f27ae4b12c4a8b09c73e`.
- Training-code Git blob SHA: `13090edb2245b5280e8affa758df5b4bf51360c3`.
- Binding `game.json` SHA-256:
  `9d6ec544143d1e5768e70b64a3d28f101d9060ad46ad2de703947654ec5eb639`.
- Counted inference: deterministic argmax after the canonical legal-action mask.
- Intended use: primary cop movement policy in counted six-gamelet play.

The policy consumes only `LocalObservation`, Bayesian `BeliefState`, and
recurrent history. Its 201 features encode own position, public barriers,
opponent scent, belief heatmap, barrier budget, step/gamelet, entropy, and
confidence. Hidden current opponent coordinates are absent. Movement and
language remain separate policies.

## Training

The selected model starts from the previous recurrent champion and adds 9,264
sequence examples from 600 population-oracle teacher games. It was optimized
for 200 distillation updates at learning rate 3e-4, seed 20260809, and retains a
128-unit recurrent state. The resulting checkpoint records 492,264 cumulative
training steps.

The teacher population included anti-loop, scent, wall, corridor, targeted,
local-adversarial, and prior learned strategies. Opponents were frozen during a
response round to avoid simultaneous-self-play collapse and to expose
non-transitive counters.

## Held-out evaluation

On the paired fixed-start ten-family tournament, with 20 six-gamelet series per
family:

- captures: 1,153/1,200, or 96.08% (Wilson 95%: 94.83%–97.04%);
- previous champion: 902/1,200, or 75.17%;
- official score: 23,295 versus 6,235;
- worst-family capture rate: 71.67%, versus 0% for the previous champion;
- p99 inference: 4.51 ms;
- technical failures: 0.

Machine evidence is under `results/rl/research_20260809/`; the complete method
and experiment inventory are in `docs/RL_RESEARCH_REPORT_20260809.md`.

## Safety, deployment, and limitations

Startup validates the manifest-selected artifact checksum, checkpoint role,
algorithm, observation width, action count, hidden size, and inference mode.
The canonical legal-action mask remains mandatory. The previous checkpoint is
retained at `models/cop_recurrent_champion.pt` for rollback but is no longer
selected by the manifest.

This remains local simulated evidence rather than an external P2P league match.
It is specialized to the binding 7×7 configuration. Run a real networked
six-gamelet series before claiming external validation.
