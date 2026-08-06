# Final Code-100 readiness report

Evidence date: 2026-08-06
State: **FINAL EXACT-SHA VERIFICATION PENDING — EXTERNAL ACTIONS PENDING**

## Candidate outcome

All implementation milestones and their direct suites pass. The next authoritative
step is `scripts/verify_100_readiness.py` from clean, committed revisions. This
document deliberately does not claim numeric 100 before that exact-current-SHA run.

The current code/evidence basis is cop
`dedaaf147989d1b63f4d4536330bf70335df4630` and thief
`55d45fcd4010884b08c64380fe03c6cd39062266`. Subsequent release-document and
verifier commits must be included in the final executable run.

## Verified implementation evidence

- Complete suites: cop 1,543 passed; thief 1,418 passed; zero skips.
- Branch coverage: both repositories exceed 89% with mandatory subsystems included.
- Frozen dependencies, lock checks, Ruff lint/format, model checksum load, hostile
  adaptive/audit/Replay/Watchdog/Gmail suites, and secret scans pass.
- A prior clean real-process acceptance completed six gamelets with 12 Step-0
  signatures, 12 passing audit signatures, two result signatures, reciprocal
  ledger consensus, two explicitly fake Gmail records, and zero public nonce values.
  A fresh exact-current-SHA process run remains part of the final verifier.

## Competitive release evidence

| Role | Exact artifact | Gamelets | Win/survival | Series wins | Worst family | Official score | p99 |
|---|---|---:|---:|---:|---:|---:|---:|
| Cop | `b9e74b7a13ca461484f2b47046eeecf8d393cb8d64b7cdd51d2915b714c21268` | 1,800 | 82.94% capture | 99.33% | 57.78% | 31,395–10,535 | 0.371 ms |
| Thief | `cdf5bc67daad6c922757dbc5aac0a278935dcbe79554e887d6003ddee2cbd271` | 1,800 | 78.72% survival | 61.67% | 55.00% | 16,085–14,745 | 0.403 ms |

Both exact checkpoints pass paired-bootstrap promotion against the strongest
heuristic, ten held-out families, zero illegal post-mask actions, and zero technical
failures. Machine results, learning curves, ablations, sensitivity, population
comparison, and notebooks are under `results/` and `notebooks/`.

## Adaptive MCP and published league-kit evidence

The adaptive pre-game chain performs transport probing, full schema introspection,
agent-produced declarative mapping, static protected-field verification, safe
conformance, signed/hashed profile locking, and deterministic gameplay adaptation.
Compatible alternate processes finish six gamelets; incompatible peers fail before
the first commitment; per-turn protocol-LLM calls are zero.

The untouched published reference-v3 clone is pinned at
`9cecfa8b4befa070dfee0f3bc23cfe7ff7216e8e`. Its 113/113 vectors pass. Real
bidirectional process checks call all four exact tools between its client/server and
ours, with locked profile
`4cc7609ea2690979e6e9776a391b2031bc838f66f306a3b2c04dadb02807decd`.
The external tree remains clean. Three failures in the kit's own test suite are an
upstream FastMCP 3.4.5 API mismatch around removed `get_tools()`; the kit was not
edited and those failures are not represented as our interoperability proof.

## Production path

`CLI → COUNTED → AgentOrchestrator → signed Step-0 → adaptive locked profile →
exactly six gamelets → canonical transition → LocalObservation + BeliefState +
recurrent champion → legal mask → Commit-Reveal → bilateral audit → identical
signed ResultAgreement → reciprocal ledgers → independent Gatekeeper → DONE`.

Counted mode fails closed on dirty/unresolvable Git, missing model, incompatible
protocol, timeout, journal failure, illegal transition, audit/result disagreement,
ledger failure, or report failure.

## External boundary

The 55-rule matrix currently contains 48 code-verifiable PASS rows, zero FAIL rows,
and seven `EXTERNAL_PENDING` rows. Full submission readiness still requires real
public/outside-group matches, real independent Gmail IDs, the real group ID, genuine
final-run GUI/Replay screenshots, official Moodle artifacts and individual
submissions, and the final audited tag push. None is fabricated here.
