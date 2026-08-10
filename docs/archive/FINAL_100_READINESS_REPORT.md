# Final Code-100 readiness report

Evidence date: 2026-08-06
State: **CODE-VERIFIABLE PASS (100/100) — EXTERNAL ACTIONS PENDING**

## Outcome

At the tagged release revision, the exact-current-SHA executable verifier must
report all 13 code-verifiable gates PASS, zero FAIL, and code-verifiable score
100. The release gate runs from fresh independent clones; its machine-readable
output is stored outside the repositories so it cannot dirty the revision it
attests. Earlier exact source evidence is retained in the release manifest.

This is not a claim that the human/external submission is complete. Public
outside-team play, real Gmail message IDs, real group identity, final GUI/Replay
screenshots, official Moodle artifacts, and individual submissions remain
`EXTERNAL_PENDING`.

## Executable quality evidence

- Frozen sync and lock checks pass in both repositories, including isolated Torch
  and NumPy imports.
- Full suites pass with zero skips: cop 1,553 tests and thief 1,428 tests.
- Actual branch coverage is cop 2,166/2,526 = 85.7482% and thief
  2,152/2,526 = 85.1940%; no broad mandatory-subsystem omission is accepted.
- The required shared `game_config.toml` is tracked in both repositories, and
  model integration tests load the manifest-selected recurrent artifact without
  relying on ignored legacy checkpoints or hidden opponent coordinates.
- Ruff lint and format, subprocess CLI startup, model schema/checksum/inference,
  hostile adaptive/audit/Replay/Watchdog/Gmail/token suites, secret scan, and
  documentation claims all pass.
- A clean real two-process counted series
  `series_20260806_212310_0ca18691` completed exactly six gamelets with
  agreement `cc752c1ca50a8c2ff6064bd92d0c97f3dec5cda4ecf25700d9dc347472162fe2`
  and reciprocal ledger consensus
  `d06a235a07c3bcca7bbb856d734d0cb4634a55723bb833668b9593a8a35c6d67`.

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
