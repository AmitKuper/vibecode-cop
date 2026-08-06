# Held-out recurrent tournament — cop

Status: **PASS** for the frozen local tournament gate. External course-group play is
`EXTERNAL_PENDING` and is not represented by these results.

| Metric | Result |
|---|---:|
| Artifact SHA-256 | `b9e74b7a13ca461484f2b47046eeecf8d393cb8d64b7cdd51d2915b714c21268` |
| Evaluation seed | 20260805 |
| Held-out series / gamelets | 300 / 1,800 |
| Captures | 1,493 (82.94%) |
| 95% gamelet confidence interval | 81.14%–84.61% |
| Series wins | 298 (99.33%) |
| Official score, cop / opponents | 31,395 / 10,535 |
| Worst-family capture rate | 57.78% |
| p50 / p95 / p99 inference | 0.234 / 0.307 / 0.371 ms |
| Technical failures / corrections | 0 / 0 |
| Promotion bootstrap 95% | +3.65 to +8.40 points/series |

Every sample is an exact six-gamelet series using official role scoring. Training
seed namespace is `[20260805, 20260805]`; held-out seeds occupy
`[20270805, 20310805]`. The ten-family population covers random, belief, wall,
local ensemble, historical checkpoint, scent, corridor, anti-loop, targeted, and
deceptive-language opponents. The weakest family is targeted exploit at 57.78%,
above the predeclared 55% floor.

The paired promotion compares the exact candidate with the strongest local-belief
heuristic under identical series seeds. It requires a strictly positive bootstrap
95% lower score bound, nonzero results in every family, zero technical failures,
p99 below 30 ms, and the role-specific worst-family floor. All conditions pass.

Authoritative machine evidence: `results/cop_held_out_tournament.json`.

## Exact-checkpoint ablations

The reproducible 5-series-per-family analysis uses the release SHA and the same ten
families. Full release captures 82.0% with +3,420 official differential versus 72.67%
and +2,860 for the strongest heuristic. Removing scent collapses capture to 36.0%;
resetting recurrent state reduces it to 80.33%. Disabling the legal mask selects an
illegal action on 44.29% of decisions and reduces capture to 65.67%. Removing barrier
actions raises the small-sample aggregate to 83.67% but lowers the worst-family rate
from 60.0% to 46.67%, so barriers remain deployed. Language on/off has exactly zero
movement-score delta because language cannot enter actor inference.

Argmax is retained: temperatures 0.25/0.5/0.75 score 80.0%/80.0%/73.0% versus 82.0%
for argmax. Population curriculum also beats the matched historical-checkpoint-only
continuation by +120 official differential. Sources:
`results/rl/strategy_analysis.json`, `results/rl/curriculum_comparison.json`, and
`notebooks/release_strategy_analysis.ipynb`.
