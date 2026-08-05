# Program Execution Ledger — vibecode-cop

## Codex Stage B/C continuation (2026-08-05)

| Milestone | Starting cop/thief SHA | Status | Executable evidence | Resulting SHA |
|---|---|---|---|---|
| M0 independent baseline | `bc8de6add8a979fa915295c71e47d2773ff244d2` / `b7a65401b64ea9fa7e48dfda83cae6d9ecc4ef61` | PASS | Both clean; frozen sync/lock pass; pytest 1308 pass vs 1181 pass + 2 skip; configured branch coverage rounded 85% with invalid omissions vs 80.76%; Ruff lint pass; format 15/9 fail; both CLI help fail; cop verifier false-positive and thief verifier absent. Baseline score 36; matrix PASS=24/FAIL=25/EXTERNAL_PENDING=6. | `71b99f3` / `2a0c139` |
| M1/M2 counted lifecycle implementation | `71b99f3` / `2a0c139` | PASS | Counted CLI/composition, signed bilateral Step-0, canonical zero-trust turns, nonce-safe bilateral audit, signed identical result agreement, reciprocal independent ledgers, deterministic adapter, and independent Gatekeeper paths pass the final real series. | `b9f6723` / `aedbcb8` |
| M3 RL calibration | `71b99f3` / `2a0c139` | PASS | Multiple weak candidates were rejected. Local-only BC warm start plus recurrent A2C established the training route later used by both promoted champions. | superseded by champion promotion |
| M3 frozen candidates | `f2fc52d` trainer / `264389a` thief inference | FAIL | 150 six-gamelet series and 900 gamelets per role, five privacy-correct held-out families. Cop argmax: 797/900 (88.56%), 150/150 series, official 16455–5015, worst 78.89%, zero technical. Thief low-temp 0.5: 578/900 (64.22%), 75/150 series, official 7390–9330, worst 16.11%, zero technical. Exact-seed Bayesian heuristic scored 7395 official thief points, so the thief candidate failed promotion and is not a champion. | cop `fd8e004`; thief `264389a`; artifacts unpromoted |

| M3 champion promotion | `97ec919` / `cebb267` | PASS | Cop champion SHA `1c6f85...6949`: 600 series/3,600 gamelets, 89.0%, official 66,060–64,980, bootstrap delta CI [0.35,3.30], worst family 79.03%, p99 0.3854 ms. Thief champion SHA `477c56...6151`: 150 series/900 gamelets, 76.11%, official 7,925–7,395, CI [2.50,4.63], worst family 34.44%, p99 0.3818 ms. Both manifests and artifacts load with exact checksums and zero technical failures. | `d2d99e2` / `f324342` |
| M1/M2 diagnostic subprocess | `97ec919` / `cebb267` plus implementation worktree | PASS (diagnostic only) | Real independent OS processes completed `series_20260805_051121_be17182b`: exit 0, exactly six gamelets, 12 valid PASSED audit signatures, 12 valid Step-0 signatures, two byte-identical result signatures, locked profile `f21ea43f...c59c`, audit bundle `277443e7...c7c`, identical ledger SHA `329f2407...12e0`, and two explicitly fake Gmail records. Active agreement SHA `db941087...b333`; passive SHA `fe94d6d7...2ef3`. Not final provenance because the tree was dirty; this defect triggered the counted CLI clean-tree guard. | pending implementation commit |
| M4 adaptive MCP | implementation worktree | PASS | Live FastMCP SSE probe/introspection and locked profile pass; compatible/incompatible fixtures, protected transforms, signed envelopes, schema/cache/agent fallbacks, conformance probes, prompt-injection rejection, and zero per-turn LLM calls are covered. Dormant LLM-per-turn adapter deleted. | `d2d99e2` / `f324342` |
| M5 quality measurement | `b9f6723` / `aedbcb8` | PASS | Strict verifier: 1,467/1,340 full tests, zero skips, 85.8130%/85.1753% actual branch coverage, Ruff/frozen locks/startup/models/tournaments/hostile suites/secret/docs and fresh two-process series all pass. | verified source revisions |

Active plan: `docs/CODEX_100_READINESS_EXECPLAN.md`. Baseline audit:
`CODEX_BASELINE_AUDIT.md`. Traceability:
`docs/REQUIREMENTS_TRACEABILITY.md`.

All code-verifiable milestones are complete. Remaining work is restricted to the
genuine public-network, outside-group, real-Gmail, group-ID, tag-push, official
PDF/screenshot, and individual Moodle actions in the external checklist.

Records all phases from Phase 0 through Phase 11.
Test counts are measured at phase end (cop repo).

| Phase | Starting SHA | Resulting SHA | Tests Before | Tests After | Description                                                      |
|-------|-------------|--------------|-------------|------------|------------------------------------------------------------------|
| 0.5   | (initial)   | 0e73947      | 0           | 569        | Reproducible green baseline, 87.71% coverage, zero Ruff violations |
| 0     | 0e73947     | e411836      | 569         | 569        | Correct five binding-rule regressions (empty audit, trapped thief, FastAPI) |
| 1     | e411836     | d5b33b2      | 569         | 600+       | Deterministic domain core, typed schemas, conformance tests, coverage gap tests |
| 1B    | d5b33b2     | e7334c3      | 600+        | 620+       | Harden ProtocolCoordinator: fail-closed handshake, final audit wiring |
| 2     | e7334c3     | c235415      | 620+        | 680+       | Single config authority, complete state commitment, six-gamelet enforcement |
| 2B    | c235415     | b1c8c26      | 680+        | 700+       | Wire ProtocolCoordinator to production path                       |
| 3     | b1c8c26     | cce9cdd      | 700+        | 750+       | Local truth types, symmetric scent, Bayesian belief engine, hint policy |
| 4     | cce9cdd     | 2e1ae88      | 750+        | 820+       | RL infrastructure, action spaces, legal masking, model schema     |
| 5     | 2e1ae88     | 1daa6cf      | 820+        | 880+       | Step-0 bilateral declarations, league ledger, lifecycle artifacts  |
| 6     | 1daa6cf     | 689580a      | 880+        | 960+       | Per-step evidence journal, transcript chain, bilateral audit and result consensus |
| 7     | 689580a     | 6ea6b2d      | 960+        | 1020+      | Deadline Tracker, independent Watchdog, recovery state, chaos tests |
| 8     | 6ea6b2d     | ed68850      | 1020+       | 1060+      | Gmail Gatekeeper pipeline: token bucket, circuit breaker, DOS detector |
| 9     | ed68850     | 8429f6f      | 1060+       | 1080+      | Live GUI belief-map app, anchored Replay app, screenshots         |
| 10    | 8429f6f     | b9c10bc      | 1080+       | 1095       | TransportPort/GameProtocolPort abstraction, capability negotiation  |
| 11    | b9c10bc     | (this commit) | 1095       | 1095       | Docs rewrite, CI pipeline, version bump to 2.0.0, release tag     |

| v7 P3 | b5de5b1 (cop) / b4dba23 (thief) | 7fddd0d (cop) / abc300e (thief) | 1120/1119 | 1163/1162 | Wire Step-0, StepJournal, Watchdog, LeagueLedger into production lifecycle |
| v7 P4 | 7fddd0d (cop) / abc300e (thief) | 7fddd0d (cop) / abc300e (thief) | 1151/1150 | 1163/1162 | Heuristic wired, strategic language policy, belief updates in turn loop |
| v7 P5 | 7fddd0d (cop) / abc300e (thief) | 9acbe85 (cop) | 1163/1162 | 1171 | SafeLiveView wired to AgentOrchestrator, GameProtocolPort, accurate README, v3.0-code-ready tag |
| v8 P1 | 9acbe85 (cop) / 336618d (thief) | (this commit) | 1171/1170 | 1182/1181+ | Fix P0-1: counted_mode propagated to PeerRuntime in run_series; Fix P0-2: PLACE_* actions use apply_joint_action so active board matches passive board |

## Notes

- "Tests Before" for phases 1–10 are approximations based on git log context.
  The definitive count at Phase 10 end is 1095 (cop) / 1094 (thief).
- Phases 2 and 2B share a single planning cycle but distinct commits.
- Phase 11 adds no new test code; count remains 1095.
- v7 Phase 3 wired: `build_step0_declaration`, `validate_counted_declaration`,
  `record_step_evidence`, `emit_heartbeat`, `start_watchdog`, `stop_watchdog`,
  `record_match_in_ledger`, `send_report_via_gatekeeper` into AgentOrchestrator;
  `run_game` calls `start_watchdog`/`stop_watchdog`; `_send_start_game` validates
  Step-0 in counted mode; `run_peer_turn` records step evidence and emits heartbeats.
- v7 Phase 5 wired: `publish_live_view` publishes SafeLiveView (no hidden coords) from
  AgentOrchestrator after each turn in `run_peer_turn`; `create_protocol_port` creates
  deterministic GameProtocolPort with locked ProtocolMapping; README rewritten with
  accurate EXTERNAL_PENDING claims; REQUIREMENTS_TRACEABILITY updated.


## Codex Stage-B / Stage-C execution (2026-08-05)

| Milestone | Exact evidence | Status |
|---|---|---|
| M1 counted root | Explicit role CLIs, clean-worktree guard, `RuntimeMode.COUNTED`, one configured Orchestrator, exact-six checks, active/passive composition tests | PASS |
| M2 zero-trust lifecycle | Bilateral signed Step-0, nonce-safe commit/reveal, canonical transitions, signed mutual audits/result, stable ledger identity, independent Gatekeeper path, token totals | PASS |
| M3 role champions | Cop `1c6f85…6949`; thief `477c56…151`; both paired held-out promotion gates pass with zero technical failures | PASS |
| M4 adaptive MCP | Live SSE introspection, declarative protected mappings, static verification, conformance probes, locked profile, incompatible pre-commit rejection, deterministic gameplay adapter | PASS |
| Final clean quality | Verified sources cop `b9f672381fb3c456a0a6fdb3f99a113750333548`, thief `aedbcb854a2e20579a1540732693d4c721955814`; 1,467/1,340 tests, zero skips; branch 1,615/1,882 = 85.8130% and 1,603/1,882 = 85.1753%; frozen sync/locks and Ruff pass. | PASS |
| Strict release verifier | 11/11 code gates PASS. Fresh real process series `series_20260805_064801_ea4d7c38`; agreement `d731f5be…3ce3`; ledger consensus `99b5f6d5…7c93`. Four external gate groups remain pending. | PASS |

## Independent hardening follow-up — 2026-08-05

| Gate | Evidence | Status |
|---|---|---|
| Frozen/isolated dependency | Frozen sync/lock plus isolated Torch 2.13.0+cpu and NumPy 2.5.1 imports in both repos | PASS |
| Adaptive discovery | 227 focused tests per repo before final HTTP/stdio additions; real process discovery, remote conformance, schema-derived fixtures, cache tamper, and schema drift | PASS |
| Full suites / coverage | Zero skips; cop 1,794/2,082 = 86.1671%; thief 1,784/2,082 = 85.6868%; current trainer measured | PASS |
| Tournament reproduction | Cop stable `959872ca…1b72`; thief `a0e2bb3d…5003`; frozen series/family results match | PASS |
| Current collection | 1,509 cop tests / 1,384 thief tests after final stdio additions | PASS |
| Clean production process | Requires coherent commit because counted mode refuses dirty trees | PENDING |
