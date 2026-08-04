# Program Execution Ledger — vibecode-cop

## Codex Stage B/C continuation (2026-08-05)

| Milestone | Starting cop/thief SHA | Status | Executable evidence | Resulting SHA |
|---|---|---|---|---|
| M0 independent baseline | `bc8de6add8a979fa915295c71e47d2773ff244d2` / `b7a65401b64ea9fa7e48dfda83cae6d9ecc4ef61` | PASS | Both clean; frozen sync/lock pass; pytest 1308 pass vs 1181 pass + 2 skip; configured branch coverage rounded 85% with invalid omissions vs 80.76%; Ruff lint pass; format 15/9 fail; both CLI help fail; cop verifier false-positive and thief verifier absent. Baseline score 36; matrix PASS=24/FAIL=25/EXTERNAL_PENDING=6. | documentation worktree, pending commit |

Active plan: `docs/CODEX_100_READINESS_EXECPLAN.md`. Baseline audit:
`CODEX_BASELINE_AUDIT.md`. Traceability:
`docs/REQUIREMENTS_TRACEABILITY.md`.

Next acceptance target is M1: one fail-closed real two-process counted composition
root and exactly-six lifecycle trace. No prior phase claim supersedes the fresh M0
runtime evidence.

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
