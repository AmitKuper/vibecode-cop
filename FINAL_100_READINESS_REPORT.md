# Final Code-100 readiness report

Evidence date: 2026-08-06
State: **CODE-VERIFIABLE PASS (100/100) — EXTERNAL ACTIONS PENDING**

## Outcome

The exact-current-SHA executable verifier reports all 13 code-verifiable gates PASS,
zero FAIL, and code-verifiable score 100 for cop
`fb9982e000488a96ea09879544b288bb661a0b98` and thief
`0c519714d709a52cb4ddbdc96d5e87b248c98687`. The final documentation/tag
commits are subjected to the same verifier from fresh clones before release; the
machine-readable verifier output is stored outside the repositories so it cannot
dirty the revision it attests.

This is not a claim that the human/external submission is complete. Public
outside-team play, real Gmail message IDs, real group identity, final GUI/Replay
screenshots, official Moodle artifacts, and individual submissions remain
`EXTERNAL_PENDING`.

## Executable quality evidence

- Frozen sync and lock checks pass in both repositories, including isolated Torch
  and NumPy imports.
- Full suites pass with zero skips: cop 1,555 tests and thief 1,430 tests.
- Actual branch coverage is cop 2,166/2,526 = 85.7482% and thief
  2,151/2,526 = 85.1544%; no broad mandatory-subsystem omission is accepted.
- Ruff lint and format, subprocess CLI startup, model schema/checksum/inference,
  hostile adaptive/audit/Replay/Watchdog/Gmail/token suites, secret scan, and
  documentation claims all pass.
- A clean real two-process counted series
  `series_20260806_070500_fd652ee5` completed exactly six gamelets with
  agreement `44b4ceb3c404f62bf44094cad24b2987c8eeddd1f85bf3d603e8d33778cd0bff`
  and reciprocal ledger consensus
  `467d5cea435c58c31d99e06329f98098c4f5253446063eaac0e4581e95f59756`.

## Competitive release evidence

| Role | Exact artifact | Gamelets | Win/survival | Series wins | Worst family | Official score | p99 |
|---|---|---:|---:|---:|---:|---:|---:|
| Cop | `b9e74b7a13ca461484f2b47046eeecf8d393cb8d64b7cdd51d2915b714c21268` | 1,800 | 82.94% capture | 99.33% | 57.78% | 31,395–10,535 | 0.371 ms |
| Thief | `cdf5bc67daad6c922757dbc5aac0a278935dcbe79554e887d6003ddee2cbd271` | 1,800 | 78.72% survival | 61.67% | 55.00% | 16,085–14,745 | 0.403 ms |

The verifier independently reproduced both 300-series/1,800-gamelet results and
their exact result hashes. Both checkpoints pass paired-bootstrap promotion,
worst-family floors, zero illegal post-mask actions, and zero technical failures.
Movement remains trained recurrent policy -> canonical legal mask -> domain
validation. Language policy is separate and does not determine movement.

## Adaptive MCP and published league-kit evidence

The pre-game pipeline performs transport probing, sanitized schema introspection,
agent-produced declarative mapping, static protected-field verification, safe
placeholder conformance, and signed/hashed profile locking. Gameplay uses only the
locked deterministic adapter and makes zero protocol-LLM calls per turn.
Compatible alternate processes finish six gamelets; incompatible semantics fail
before the first commitment.

The untouched `Imreec/copthief-league-protocol` clone remains clean at
`9cecfa8b4befa070dfee0f3bc23cfe7ff7216e8e`. All 113 published vectors pass.
Real processes prove both directions: its unmodified client calls our exact
four-tool FastMCP surface, and our discovered client calls its unmodified server.
The locked profile is
`4cc7609ea2690979e6e9776a391b2031bc838f66f306a3b2c04dadb02807decd`.

The bridge intentionally preserves the kit's push-only `reference-v3` semantics:
`negotiate(message)`, `receive_turn(message)`, `submit_audit(payload)`, and
`receive_control(message)`; move and nonce stay private until bilateral audit.

## Production path

`CLI -> COUNTED -> AgentOrchestrator -> signed bilateral Step-0 -> adaptive locked
profile -> exactly six gamelets -> canonical transition -> LocalObservation +
BeliefState + recurrent champion -> legal mask -> Commit-Reveal -> bilateral
comprehensive audit -> identical signed ResultAgreement -> reciprocal league
ledgers -> independent Gatekeeper reports -> DONE`.

Counted mode fails closed on dirty/unresolvable Git, missing or incompatible model,
incompatible protocol, timeout, journal failure, illegal transition, audit/result
disagreement, ledger failure, or reporting failure. It never silently substitutes
`STAY` for a peer violation and never downgrades to development mode.

## External boundary

The 55-rule matrix contains 48 PASS, zero FAIL, and seven
`EXTERNAL_PENDING` rows. The code-verifiable score is 100/100; full submission
readiness remains false until those genuine external actions are completed. Local
fixtures, fake Gmail, illustrative screenshots, generated identities, and
localhost tunnels are not represented as real-world evidence.
