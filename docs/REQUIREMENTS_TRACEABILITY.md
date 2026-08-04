# Requirements Traceability Matrix — Appendix-E (55 Rules)

**Product:** Cop vs Thief P2P Game  
**Release:** v3.0-code-ready (cop: Phase 5 v7)  
**Date:** 2026-08-04  
**Phase pack:** v7 (Phases 1–5 v7)

**Status legend:**
- `PASS` — directly supported by code, tests, and evidence in this repo
- `EXTERNAL_PENDING` — code is ready; real external action (opponent, credentials, Moodle) required
- `FAIL` — incomplete; honest assessment; must be fixed before final submission

---

## Rules 1–10: Architecture and Local Epistemology

| # | Rule | Implementation | Test Evidence | Status |
|---|------|---------------|---------------|--------|
| 1 | Two independent processes — cop and thief run as separate OS processes with no shared memory space | `agent/peer_runtime.py` (PeerRuntime); each role launched independently; ports are distinct; watchdog launched as subprocess | Architecture-by-design; OS process isolation; `start_watchdog()` in AgentOrchestrator uses `subprocess.Popen` | PASS |
| 2 | No shared memory — neither process may read the other's internal state at runtime | Independent configs/logs/ports; no IPC beyond MCP JSON-RPC; architecture enforced by OS | Network-only comms enforced in `agent/mcp/transport_port.py` | PASS |
| 3 | Orchestrator single entry point — one object is sole authority for all state mutations | `AgentOrchestrator` is single composition root (v7); owns belief, scent, language, journal, watchdog, live view, protocol port | `tests/test_agent_orchestrator.py`; all subsystem access via orchestrator | PASS |
| 4 | Proper state machine — protocol follows a well-defined 16-state FSM | `ProtocolState` (16 states): IDLE → STEP0_NEGOTIATING → READY → COMPUTING_MOVE → COMMIT_SENT/RECEIVED → BOTH_COMMITTED → REVEAL_SENT/RECEIVED → STEP_VERIFIED → AUDITING → RESULT_AGREEMENT → REPORTING → DONE / TECHNICAL_LOSS / ABORTED | `agent/mcp/protocol.py` defines all states; coordinator enforces transitions | PASS |
| 5 | Illegal transitions rejected — guard functions reject all out-of-sequence state changes | `ProtocolStateMachine.transition()` validates against `_ALLOWED` set; raises `ProtocolError` on illegal move | 45+ integration tests in `agent/tests/test_coordinator*.py` | PASS |
| 6 | Deadline tracker — per-request deadline with bounded timeouts, retry, and exponential backoff | `DeadlineTracker` in `agent/reliability/deadline_tracker.py`; `timeout_s`, `max_attempts`, exponential backoff in `next_retry_delay()` | `tests/test_deadline_tracker.py` | PASS |
| 7 | Watchdog — independent OS-process watchdog monitors the main process | `launch_watchdog_subprocess()` in `agent/reliability/watchdog.py` uses `subprocess.Popen`; `AgentOrchestrator.start_watchdog()` called in `run_game()`; skipped in DEVELOPMENT mode | `tests/test_watchdog.py`; `start_watchdog` wired in `peer_runtime.py` | PASS |
| 8 | Local truth GUI — live view exposes only local truth; no hidden coordinates | `AgentOrchestrator.publish_live_view()` (Phase 5 v7) wired into `run_peer_turn()` after each step; `_verify_no_hidden_coord()` in LiveViewModel enforces no opponent coords | `tests/test_gui_production_wiring.py`; `tests/test_live_view_model.py` | PASS |
| 9 | No full objective GUI — SafeLiveView has no opponent position field | `SafeLiveView` defined in `agent/observation.py` without `opponent_position`; `_verify_no_hidden_coord` enforces this | Test asserts `opponent_position` absent from all SafeLiveView instances | PASS |
| 10 | Public tunneling — game port accessible via public tunnel for remote opponents | `docs/DEPLOYMENT_TUNNEL_RUNBOOK.md` documents ngrok/cloudflared procedure | Runbook present; real tunnel evidence requires separate machines | EXTERNAL_PENDING |

## Rules 11–16: Physics and Configuration

| # | Rule | Implementation | Test Evidence | Status |
|---|------|---------------|---------------|--------|
| 11 | Byte-identical config — both peers use the same canonical configuration | `CanonicalConfig.config_sha256` in `agent/config/canonical_config.py`; `scent_model_hash` in `PeerDeclaration`; configs compared during Step-0 | `tests/test_canonical_config.py` (47 tests) | PASS |
| 12 | Minimum/fixed values — grid≥7, barriers≥14, turns≥35; scoring values are fixed | `FieldKind.MINIMUM` / `FieldKind.FIXED` in `agent/config/canonical_config.py`; `_FIELD_SPECS` enforces floor values and exact values | `tests/test_canonical_config.py` (47 tests) | PASS |
| 13 | Orthogonal movement — only N/S/E/W/STAY directions allowed | `MOVE_DELTAS = {"N": (-1,0), "S": (1,0), "E": (0,1), "W": (0,-1), "STAY": (0,0)}` in `agent/rl/action_space.py`; no diagonal entries | Action mask tests; domain conformance tests | PASS |
| 14 | No diagonal movement — diagonal deltas not present in legal action set | `MOVE_DELTAS` contains only cardinal+stay; no `NE/NW/SE/SW` keys | Adversarial action mask tests verify illegal actions rejected | PASS |
| 15 | Every barrier openly declared — barriers committed before play in Step-0 | Barriers in `build_board_state()`; commitment hash in `StepEvidence`; `PeerDeclaration.config_sha256` includes barrier placement | `tests/test_step_evidence.py`; `tests/test_barrier_commitment.py` | PASS |
| 16 | No false barrier location — barriers derived from domain state; fabrication impossible | Barriers derived from `Board` domain state; no separate barrier-list variable that could diverge; Step-0 evidence locks values | Domain conformance tests; `TestBarrierOnThiefCapture` | PASS |

## Rules 17–24: Cryptography

| # | Rule | Implementation | Test Evidence | Status |
|---|------|---------------|---------------|--------|
| 17 | SHA-256 Commit-Reveal — h\_commit = SHA-256(move‖nonce‖game\_id‖gamelet‖step‖role‖state\_hash‖hint‖intent) | `create_commitment()` in `agent/mcp/crypto.py`: `h_commit = hashlib.sha256(canonical.encode("utf-8")).hexdigest()` | `tests/test_crypto.py`; `commit_hash_for` unit tests | PASS |
| 18 | Nonce secret until final audit — nonce stored locally; not transmitted until reveal phase | `RecoveryState.local_nonces` stores nonce; only sent in REVEAL message after both commits received | `tests/test_crypto.py`; protocol sequence tests | PASS |
| 19 | Mismatch → technical loss — hash mismatch triggers TECHNICAL\_LOSS state | `coordinator.on_technical_loss()` called when `verify_commitment()` returns False; SM transitions to TECHNICAL_LOSS | `tests/test_coordinator_transitions.py` | PASS |
| 20 | Replay Viewer — post-game replay with signature and hash-chain verification | `ReplayApp` in `agent/replay/replay_app.py`; verifies Ed25519 signature on `ResultAgreement`; `journal.verify_chain()` validates hash chain | Code verified; live screenshots require external session | EXTERNAL_PENDING |
| 21 | Truthful capture declaration — capture derived from domain transition, not self-report | Domain `rules_outcomes.check_game_status()` derives capture from `cop_position == thief_position`; not from peer declaration | `TestTruthfulCapture`; domain conformance suite | PASS |
| 22 | False capture rejected — capture requires positional equality in domain; adversarial checks | Capture gated on `cop_pos == thief_pos` in domain engine; adversarial tests attempt false capture | `TestFalseCaptureRejected`; `TestBarrierOnThiefCapture` | PASS |
| 23 | Scent model locked — scent parameters committed in Step-0 declaration | `scent_model_hash` in `PeerDeclaration` (declaration.py line 62); `ScentFields` 5×5 kernel in `agent/scent.py` (KERNEL_RADIUS=2) | `tests/test_scent.py`; `tests/test_declaration.py` | PASS |
| 24 | Hardware declaration — OS/CPU/RAM/GPU info declared in Step-0 | `PeerDeclaration.os_info`, `.cpu_info`, `.ram_gb`, `.gpu_info` in `agent/step0/declaration.py`; `validate_for_counted_mode()` checks placeholders | `tests/test_validator.py`; `tests/test_declaration.py` | PASS |

## Rules 25–30: Strategy, Language, Gmail Protection

| # | Rule | Implementation | Test Evidence | Status |
|---|------|---------------|---------------|--------|
| 25 | LLM movement recommendation — RL model provides competitive move recommendations | RL infrastructure complete (PPO/DQN in `agent/rl/`); `.pt` files exist in `models/` but `models/MANIFEST.json` records `training_steps: 0` and `evaluation_win_rate: 0.0` — weights are placeholder-initialized, not competitively trained | `tests/test_rl_*.py` test infrastructure only; no trained evaluation passes | FAIL — model files present but MANIFEST confirms zero training steps and zero win rate; real GPU training required |
| 26 | Free natural language — hints use template-based natural language; no coordinates | `NaturalLanguagePolicy` in `agent/language/deception_policy.py`; `generate_strategic_hint()` in `AgentOrchestrator` wired into `run_peer_turn()`; `DeceptionIntent` (TRUTH/LIE/AMBIGUOUS/BLUFF) | `tests/test_deception_policy.py`; `tests/test_hint_policy.py` | PASS |
| 27 | No numeric-location verbal protocol — hints use direction names only | `generate_hint()` maps moves to `DIRECTION_NAMES` (`{"N": "north", "S": "south", ...}`); no numeric row/column coordinates; `hint_is_numeric_location` guard in validator | `tests/test_hint_policy.py`; no numeric coords in any template string | PASS |
| 28 | Token bucket — rate-limiting with continuous monotonic refill | `TokenBucket` in `agent/gmail/token_bucket.py`; `time.monotonic()` refill; thread-safe `consume()` | 7 unit tests in `tests/test_token_bucket.py` | PASS |
| 29 | DOS detector — burst/repeated-game-id detection with circuit breaker | `DosDetector` in `agent/gmail/dos_detector.py`; `CircuitBreaker` in `agent/gmail/circuit_breaker.py`; integrated in `Gatekeeper` pipeline | `tests/test_dos_detector.py`; `tests/test_circuit_breaker.py` | PASS |
| 30 | Send-only Gmail — OAuth scope limited to `gmail.send` | `docs/GMAIL_REPORTING_RUNBOOK.md` specifies `gmail.send` scope; `agent/gmail/gatekeeper.py` uses send-only API path | Runbook documented; real OAuth credentials require external setup | EXTERNAL_PENDING |

## Rules 31–45: League and Submission

| # | Rule | Implementation | Test Evidence | Status |
|---|------|---------------|---------------|--------|
| 31 | Minimum different groups — ledger enforces at least 2 distinct opponents | `MIN_DIFFERENT_GROUPS = 2` in `agent/step0/league_ledger.py`; `validate_before_append()` enforces; `has_minimum_opponents()` checks | `tests/test_league_ledger.py` | EXTERNAL_PENDING — code enforces; real matches require external opponents |
| 32 | Automatic Gmail report — Gatekeeper sends result report automatically after game series | `Gatekeeper` pipeline in `agent/gmail/gatekeeper.py`; `RECIPIENT = "rmisegal+uoh26finalgame@gmail.com"`; `ResultAgreement` JSON attached | `tests/test_gatekeeper.py` (fake-service tests) | EXTERNAL_PENDING — real Gmail send requires OAuth credentials |
| 33 | Valid JSON report — report body is valid JSON; schema validated before send | `ResultAgreement.canonical_bytes()` produces valid JSON; Gatekeeper validates `body.startswith('{')` | `tests/test_result_consensus.py` | PASS |
| 34 | No free-text final report — body must start with `{` (JSON) or GatekeeperError raised | `Gatekeeper._validate_body()` checks `body.startswith('{')` and raises `GatekeeperError` otherwise | `tests/test_gatekeeper.py::test_non_json_body_rejected` | PASS |
| 35 | Bilateral result agreement and dual sends — both peers sign and send the result | `SignedResultAgreement` and `verify_bilateral_consensus()` in `agent/audit/result_consensus.py`; both send to RECIPIENT | Code verified; real bilateral send requires external session | EXTERNAL_PENDING |
| 36 | Mutual comprehensive audit — bilateral AuditSummary with consensus verification | `AuditSummary` in `agent/audit/audit_summary.py`; `verify_bilateral_consensus()` in `agent/audit/result_consensus.py` | `tests/test_audit_summary.py`; `tests/test_result_consensus.py` | PASS |
| 37 | Accurate counted-match declaration — `previous_counted_matches` in PeerDeclaration; ledger enforces | `PeerDeclaration.previous_counted_matches` (declaration.py line 68); `LeagueLedger` tracks and validates | `tests/test_declaration.py`; `tests/test_league_ledger.py` | PASS |
| 38 | False declaration disqualification — `validate_for_counted_mode()` detects placeholder/false values | `validate_for_counted_mode()` in `agent/step0/validator.py` checks git_sha, group_id (8 chars, not placeholder), model_sha256 | `tests/test_validator.py` | PASS |
| 39 | No secrets in repo — credentials.json/token.json excluded; CI secret scan passes | `.gitignore` covers `credentials.json`, `token.json`, `secrets/`, `*.credentials.json`, `*.token.json` | CI pipeline secret scan; `.gitignore` verified | PASS |
| 40 | Credentials in .gitignore — all credential patterns explicitly listed | `.gitignore` lines 9–13 explicitly list all credential file patterns | `.gitignore` content verified | PASS |
| 41 | Documented Git tag — v2.0-submission tag created; v1.0-submission preserved | Tags `v1.0-submission` and `v2.0-submission` on main branch | `git tag` output; `docs/RELEASE_CHECKLIST.md` | PASS |
| 42 | Academic README — README contains full academic content per spec | `README.md` rewritten in Phase 11 with architecture, protocol, installation, configuration, testing sections | README.md at repo root | PASS |
| 43 | Moodle unchanged-layout PDF — submission PDF with original layout | `docs/RELEASE_CHECKLIST.md` documents PDF requirement | PDF generation and Moodle upload requires external action | EXTERNAL_PENDING |
| 44 | Individual Moodle submission — each team member submits separately | Noted in `docs/RELEASE_CHECKLIST.md` | Each member must submit individually on Moodle | EXTERNAL_PENDING |
| 45 | Unique eight-character group ID — validator enforces exactly 8 chars; not placeholder | `validate_for_counted_mode()`: `len(decl.group_id) != 8` → error; `PLACEHOLDER_GROUP_IDS` check | `tests/test_validator.py`; validator rejects `len != 8` | EXTERNAL_PENDING — validator code enforces; real group ID assigned by course |

## Rules 46–55: Cross-Checked Requirements

| # | Rule | Implementation | Test Evidence | Status |
|---|------|---------------|---------------|--------|
| 46 | Barrier-on-thief capture — placing a barrier on the thief's cell is a legal cop win | `apply_place_action()` in `agent/rl/env_helpers.py`; `check_game_status()` detects barrier-on-thief capture | `TestBarrierOnThiefCapture` (4 tests) | PASS |
| 47 | Trapped thief capture — thief with no orthogonal escape (STAY excluded) is cop win | `Board.has_orthogonal_escape()` in `agent/board.py`; `check_game_status()` uses it | `TestTrappedThiefSemantics` (7 tests) | PASS |
| 48 | Scoring table — fixed scoring vector: capture\_cop=20, capture\_thief=5, survival\_cop=5, survival\_thief=10, diversity=10 | `FieldKind.FIXED` entries in `_FIELD_SPECS` in `agent/config/canonical_config.py` lines 47–50 | `tests/test_canonical_config.py` | PASS |
| 49 | Two repositories / cross-links — cop and thief repos cross-reference each other | `README.md` in both repos contains companion-repo link section | README.md in both repos | PASS |
| 50 | README/config/PRD/PLAN/TODO — all required files present | `README.md`, `PRD.md`, `PLAN.md`, `TODO.md` at repo root; `game_config.toml` + `config.toml.example` | `ls` of repo root confirms all files | PASS |
| 51 | Correct report address — RECIPIENT = "rmisegal+uoh26finalgame@gmail.com" | `RECIPIENT = "rmisegal+uoh26finalgame@gmail.com"` in `agent/gmail/gatekeeper.py` line 11 | Code grep verified | PASS |
| 52 | One counted match per opponent — LeagueLedger.validate_before_append enforces | `validate_before_append()` in `agent/step0/league_ledger.py` line 81; prevents duplicate counted entries | `tests/test_league_ledger.py` | PASS |
| 53 | Git SHA in Step-0 — PeerDeclaration.git_sha; validate_for_counted_mode rejects placeholder | `PeerDeclaration.git_sha` (declaration.py line 30); `validate_for_counted_mode()` rejects empty/placeholder/unknown | `tests/test_validator.py` | PASS |
| 54 | Token totals in final JSON — ResultAgreement.token_totals and AuditSummary.token_totals fields present | `ResultAgreement.token_totals: dict` (audit/result_consensus.py line 28); `AuditSummary.token_totals: dict` (audit/audit_summary.py line 25) | `tests/test_audit_summary.py`; `tests/test_result_consensus.py` | PASS |
| 55 | Self-grade code quality only — self-grading based on code quality, not external match outcomes | Noted in `docs/RELEASE_CHECKLIST.md`; self-grading rubric in PRD | Acknowledged in release documentation | EXTERNAL_PENDING |

---

## Summary

| Status | Count | Rules |
|--------|------:|-------|
| PASS | 44 | 1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 13, 14, 15, 16, 17, 18, 19, 21, 22, 23, 24, 26, 27, 28, 29, 33, 34, 36, 37, 38, 39, 40, 41, 42, 46, 47, 48, 49, 50, 51, 52, 53, 54 |
| EXTERNAL_PENDING | 10 | 10, 20, 30, 31, 32, 35, 43, 44, 45, 55 |
| FAIL | 1 | 25 (RL: placeholder model weights, training_steps=0, win_rate=0.0) |

**Total:** 55 rules

**v7 Phase 5 changes (2026-08-04):**
- Rule 1: EXTERNAL_PENDING → PASS (watchdog subprocess wired; two-process isolation demonstrated in DEVELOPMENT mode)
- Rule 3: PASS (AgentOrchestrator confirmed as single composition root in v7)
- Rule 7: PASS (start_watchdog wired in run_game; skipped in DEVELOPMENT, active in WARMUP/COUNTED)
- Rule 8: PASS (publish_live_view wired in run_peer_turn after every step)
- Rule 26: PASS (generate_strategic_hint wired from AgentOrchestrator into turn loop)
- Rule 27: PASS (hint_is_numeric_location guard confirmed)

> Rule 25 is FAIL because `models/MANIFEST.json` records `training_steps: 0` and `evaluation_win_rate: 0.0`. The `.pt` files are placeholder-weight files, not competitively trained models. Real training on GPU is required before submission.
