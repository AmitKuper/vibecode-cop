# Held-out recurrent tournament — cop

Status: **PASS** for the frozen local tournament gate. External course-group play
remains `EXTERNAL_PENDING` and is not represented by this result.

| Metric | Result |
|---|---:|
| Evaluation seed | 20260805 |
| Held-out series / gamelets | 600 / 3,600 |
| Gamelet wins | 3,204 (89.00%) |
| 95% gamelet confidence interval | 87.94%–89.98% |
| Series wins | 600 (100.00%) |
| Official score, cop / opponents | 66,060 / 19,980 |
| Worst opponent-family win rate | 79.03% |
| Technical failures / illegal corrections | 0 / 0 |
| Promotion bootstrap 95% | +0.35 to +3.30 points per series |

The five held-out families are random, belief pursuit/evasion, wall-biased,
local adversarial ensemble, and a historical thief checkpoint. Every sample is an
exact six-gamelet series using official role scoring. The paired promotion compares
the champion with the strongest local-belief heuristic under the same seeds and
requires a positive 95% lower bound, nonzero results in every family, zero technical
failures, and p99 inference below 30 ms.

Authoritative machine evidence: `results/cop_held_out_tournament.json`.
