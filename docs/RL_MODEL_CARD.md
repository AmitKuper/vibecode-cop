# RL policy model card — cop

Status: **DEPLOYED / LOCAL GATE PASS**. External league play remains
`EXTERNAL_PENDING`.

## Identity and intended use

- Role: cop; grid: 7×7; algorithm: recurrent A2C with a GRUCell policy/value head.
- Artifact: `models/cop_recurrent_champion.pt`.
- SHA-256: `b9e74b7a13ca461484f2b47046eeecf8d393cb8d64b7cdd51d2915b714c21268`.
- Training-code SHA: `e052b799e1f732cd140fe3b51af6165566c239c9`.
- Counted inference: deterministic argmax after the canonical legal-action mask.
- Intended use: primary cop movement policy in counted six-gamelet play.

The policy consumes only `LocalObservation`, Bayesian `BeliefState`, and recurrent
history. Features encode own position, public barriers, opponent scent, belief
heatmap, own barrier budget, step/gamelet, entropy, and confidence. Hidden current
opponent coordinates are absent. Movement and language are separate policies.

## Training

The champion descends from a 240-demonstration local-belief behavioral-cloning warm
start and recurrent A2C. It was continued to 11,800 episodes (at most 413,000
environment steps) with a 128-unit recurrent state, gamma 0.99, final learning rate
1e-5, seed 20260805, and historical thief checkpoint
`b1769c9e67ce571efa971a345e08a10d9c33a5710e6eb7ce0c8896a1b2feab5c`.

The final curriculum retains all ten evaluation families and oversamples the
predeclared targeted-evasion weakness. Belief-supported trap shaping rewards only
public barrier changes that reduce exits near belief mass; it receives no hidden
coordinate. Candidate promotion was frozen at a 55% worst-family capture floor.

## Held-out evaluation

The exact artifact passed 300 held-out six-gamelet series (1,800 gamelets):

- capture rate 82.94% (95% CI 81.14%–84.61%);
- series win rate 99.33% (95% CI 97.60%–99.82%);
- official score 31,395 versus 10,535;
- worst-family capture rate 57.78%;
- paired official-score improvement over the strongest heuristic: +6.05 points per
  series, bootstrap 95% CI +3.65 to +8.40;
- p99 inference 0.371 ms; technical failures and action corrections: 0.

The ten families are random, belief pursuit/evasion, wall, local adversarial
ensemble, historical checkpoint, scent-following, corridor-cutting, anti-loop,
targeted exploit, and deceptive language. Machine evidence is
`results/cop_held_out_tournament.json`.

## Safety, deployment, and limitations

Counted startup validates the artifact checksum, schema versions, role, grid size,
and positive trained/evaluated metadata. Missing or incompatible artifacts fail
closed; the heuristic is a development fallback only. The legal mask is followed by
canonical domain validation before every physical action.

This is local simulated evidence, not evidence against another course group. It is
specialized to the binding 7×7 rules. Targeted evasion remains the weakest family,
and model behavior outside the evaluated observation/action schemas is unsupported.
