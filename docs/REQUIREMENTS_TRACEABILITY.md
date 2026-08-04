# Requirements Traceability Matrix — Appendix-E (55 Rules)

**Product:** Cop vs Thief P2P Game  
**Release:** v3.0-code-ready → v8 remediation in progress (cop: 7ab1b11, thief: caa49f7)  
**Date:** 2026-08-04  
**Phase pack:** v8 (Phases 1–6 v8 — Rule 25 reclassified per v8 spec; Rules 35/36 fixed)

**Status legend:**
- `PASS` — code exists AND called from real production path (AgentOrchestrator → PeerRuntime → turn loop) AND a test proves the behavior
- `EXTERNAL_PENDING` — code is ready; a real external action (opponent, credentials, Moodle) is the only remaining blocker
- `FAIL` — incomplete even if component exists; not wired end-to-end in production

**v7 Strict Criteria (tighter than v6):** PASS requires all three conditions: (1) code exists, (2) it is called from the real production path, AND (3) a test proves the behavior. "Component exists" alone is not sufficient.

---

## Rules 1–10: Architecture and Local Epistemology

| # | Rule | Production Code | Test Evidence | Status |
|---|------|----------------|---------------|--------|
| 1 | Two independent processes — cop and thief run as separate OS processes with no shared memory space | `agent/peer_runtime.py` (PeerRuntime); each role launched independently; `AgentOrchestrator.start_watchdog()` called in `peer_runtime.py:152` uses `subprocess.Popen` to launch watchdog as separate process | `tests/test_two_process_integration.py`; `tests/test_watchdog.py`; watchdog subprocess wired into production lifecycle | PASS |
| 2 | No shared memory — neither process may read the other's internal state at runtime | Independent configs/logs/ports per role; no IPC beyond MCP JSON-RPC; OS process isolation enforced by process model | Network-only comms enforced via `agent/mcp/transport_port.py`; architecture test suite | PASS |
| 3 | Orchestrator single entry point — one object is sole authority for all state mutations | `AgentOrchestrator` at `agent/agent_orchestrator.py:18` is composition root; owns belief, scent, language, journal, watchdog, live view; `PeerRuntime` holds sole reference | `tests/test_agent_orchestrator.py`; `tests/test_orchestrator_lifecycle.py`; `tests/test_runtime_mode.py` | PASS |
| 4 | Proper state machine — protocol follows a well-defined 16-state FSM | `ProtocolState` (16 states) in `agent/mcp/coordinator.py`; IDLE → STEP0_NEGOTIATING → READY → COMPUTING_MOVE → COMMIT_SENT → BOTH_COMMITTED → REVEAL_SENT → STEP_VERIFIED → AUDITING → RESULT_AGREEMENT → REPORTING → DONE / TECHNICAL_LOSS / ABORTED | `agent/mcp/protocol.py` defines states; coordinator tests | PASS |
| 5 | Illegal transitions rejected — guard functions reject all out-of-sequence state changes | `ProtocolStateMachine.transition()` validates against `_ALLOWED` set; raises `ProtocolError` on illegal move; called at every turn boundary | 45+ integration tests in `tests/test_coordinator*.py`; adversarial SM tests | PASS |
| 6 | Deadline tracker — per-request deadline with bounded timeouts, retry, and exponential backoff | `DeadlineTracker` created at `agent/agent_orchestrator.py:68` in `AgentOrchestrator.__init__`; `timeout_s`, `max_attempts`, exponential backoff in `next_retry_delay()` | `tests/test_deadline_tracker.py`; `tests/test_production_lifecycle_integration.py` | PASS |
| 7 | Watchdog — independent OS-process watchdog monitors the main process | `AgentOrchestrator.start_watchdog()` called at `agent/peer_runtime.py:152` in `run_game()`; `launch_watchdog_subprocess()` uses `subprocess.Popen`; skipped in DEVELOPMENT mode | `tests/test_watchdog.py`; `tests/test_orchestrator_lifecycle.py::test_start_watchdog_sets_paths` | PASS |
| 8 | Local truth GUI — live view exposes only local truth; no hidden coordinates | `AgentOrchestrator.publish_live_view()` called at `agent/peer_turn_loop.py:198` inside `run_peer_turn()` after every step; `_verify_no_hidden_coord()` in LiveViewModel enforces no opponent coords | `tests/test_gui_production_wiring.py`; `tests/test_live_view_model.py`; `tests/test_hidden_coord_leak_production.py` | PASS |
| 9 | No full objective GUI — SafeLiveView has no opponent position field | `SafeLiveView` in `agent/observation.py` has no `opponent_position` field; `_verify_no_hidden_coord` raises on any hidden coord | Tests assert `opponent_position` absent from all SafeLiveView instances | PASS |
| 10 | Public tunneling — game port accessible via public tunnel for remote opponents | `docs/DEPLOYMENT_TUNNEL_RUNBOOK.md` documents ngrok/cloudflared procedure; `GameProtocolPort` abstraction in production | Runbook present; real tunnel evidence requires separate machines connected live | EXTERNAL_PENDING |

## Rules 11–16: Physics and Configuration

| # | Rule | Production Code | Test Evidence | Status |
|---|------|----------------|---------------|--------|
| 11 | Byte-identical config — both peers use the same canonical configuration | `CanonicalConfig.config_sha256` in `agent/config/canonical_config.py`; `scent_model_hash` in `PeerDeclaration`; `config_sha256` transmitted in every protocol message; configs compared during Step-0 exchange | `tests/test_canonical_config.py` (47 tests); `tests/test_shared_config_contract.py` | PASS |
| 12 | Minimum/fixed values — grid≥7, barriers≥14, turns≥35; scoring values are fixed | `FieldKind.MINIMUM` / `FieldKind.FIXED` in `_FIELD_SPECS` (`agent/config/canonical_config.py`); floor values and exact values enforced on load | `tests/test_canonical_config.py` (47 tests); `tests/test_config_conformance.py` | PASS |
| 13 | Orthogonal movement — only N/S/E/W/STAY directions allowed | `MOVE_DELTAS = {"N":(-1,0),"S":(1,0),"E":(0,1),"W":(0,-1),"STAY":(0,0)}` at `agent/rl/action_space.py:10`; no diagonal entries; `RulesEngine.validate_move()` rejects others | Action mask tests; domain conformance tests; `tests/test_compliance.py` | PASS |
| 14 | No diagonal movement — diagonal deltas not present in legal action set | `MOVE_DELTAS` contains exactly 5 keys (N/S/E/W/STAY); NE/NW/SE/SW absent; adversarial tests verify illegal actions rejected | Adversarial action mask tests; `tests/test_domain_conformance.py` | PASS |
| 15 | Every barrier openly declared — barriers committed before play in Step-0 | Barriers in `build_board_state()` (`agent/peer_turn_helpers.py:229`); commitment hash in `StepEvidence`; `PeerDeclaration.config_sha256` includes barrier placement | `tests/test_step_evidence.py`; `tests/test_barrier_commitment.py` | PASS |
| 16 | No false barrier location — barriers derived from domain state; fabrication impossible | Barriers derived from `Board` domain state; no separate barrier list that could diverge; Step-0 evidence locks values; `build_board_state()` reads `runtime.board.barriers` directly | Domain conformance tests; `tests/test_compliance.py` | PASS |

## Rules 17–24: Cryptography

| # | Rule | Production Code | Test Evidence | Status |
|---|------|----------------|---------------|--------|
| 17 | SHA-256 Commit-Reveal — h\_commit = SHA-256(move‖nonce‖game\_id‖gamelet‖step‖role‖state\_hash‖hint‖intent) | `create_commitment()` at `agent/mcp/crypto.py:42`: `h_commit = hashlib.sha256(canonical.encode("utf-8")).hexdigest()`; called from `run_peer_turn()` at `peer_turn_loop.py:85` | `tests/test_crypto.py`; commit-reveal unit tests | PASS |
| 18 | Nonce secret until final audit — nonce stored locally; not transmitted until reveal phase | `RecoveryState.local_nonces` stores nonce; only sent in REVEAL message payload after both commits exchanged; nonce never in COMMIT message | `tests/test_crypto.py`; protocol sequence tests | PASS |
| 19 | Mismatch → technical loss — hash mismatch triggers TECHNICAL\_LOSS state | `coord.on_technical_loss()` called at `peer_turn_loop.py:109,115,134,140` when commit/reveal fails; SM transitions to TECHNICAL_LOSS | `tests/test_coordinator_transitions.py`; `tests/test_two_process_integration.py` | PASS |
| 20 | Replay Viewer — post-game replay with signature and hash-chain verification | `ReplayApp` at `agent/replay/replay_app.py`; verifies Ed25519 signature on `ResultAgreement`; `journal.verify_chain()` validates hash chain; code complete | Code verified; live screenshots require external game session | EXTERNAL_PENDING |
| 21 | Truthful capture declaration — capture derived from domain transition, not self-report | `rules_engine.check_game_status()` derives capture from `cop_position == thief_position`; never from peer declaration | `TestTruthfulCapture`; domain conformance suite | PASS |
| 22 | False capture rejected — capture requires positional equality in domain; adversarial checks | Capture gated on `cop_pos == thief_pos` in domain engine; adversarial tests attempt false capture and verify rejection | `TestFalseCaptureRejected`; `tests/test_rl_tools_reports.py::test_capture_returns_cop_win` | PASS |
| 23 | Scent model locked — scent parameters committed in Step-0 declaration | `scent_model_hash` field at `agent/step0/declaration.py:62` in `PeerDeclaration`; `ScentFields` 5×5 kernel in `agent/scent.py` (KERNEL_RADIUS=2); populated by `build_step0_declaration()` | `tests/test_scent.py`; `tests/test_step0_declarations.py` | PASS |
| 24 | Hardware declaration — OS/CPU/RAM/GPU info declared in Step-0 | `PeerDeclaration.os_info`, `.cpu_info`, `.ram_gb`, `.gpu_info` at `agent/step0/declaration.py`; populated at `agent/agent_orchestrator.py:288–289` using `platform.platform()` / `platform.processor()`; `validate_for_counted_mode()` checks placeholders | `tests/test_orchestrator_lifecycle.py::test_build_step0_declaration_fields`; `tests/test_validator.py` | PASS |

## Rules 25–30: Strategy, Language, Gmail Protection

| # | Rule | Production Code | Test Evidence | Status |
|---|------|----------------|---------------|--------|
| 25 | LLM movement recommendation — RL model provides competitive move recommendations | RL infrastructure complete (PPO/DQN in `agent/rl/`); `models/MANIFEST.json` records `training_steps: 0` and `evaluation_win_rate: 0.0` — placeholder weights; heuristic fallback active in production | `tests/test_rl_*.py` test infrastructure only | EXTERNAL_PENDING — per v8 spec, Rule 25 is RECOMMENDED not mandatory; untrained model is a competitive gap, not a formal rule violation; real GPU training required |
| 26 | Free natural language — hints use template-based natural language; no coordinates | `NaturalLanguagePolicy` at `agent/language/deception_policy.py:17`; `AgentOrchestrator.generate_strategic_hint()` called at `peer_turn_loop.py:75`; `DeceptionIntent` (TRUTH/LIE/AMBIGUOUS/BLUFF); wired into every turn | `tests/test_deception_policy.py`; `tests/test_hint_policy.py` | PASS |
| 27 | No numeric-location verbal protocol — hints use direction names only | `generate_hint()` maps moves to `DIRECTION_NAMES` (north/south/east/west); no numeric row/column coordinates; `hint_is_numeric_location()` guard at `deception_policy.py:92`; tested that all templates pass guard | `tests/test_deception_policy.py` (7 tests); `tests/test_hint_policy.py` | PASS |
| 28 | Token bucket — rate-limiting with continuous monotonic refill | `TokenBucket` at `agent/gmail/token_bucket.py:7`; `time.monotonic()` refill; thread-safe `consume()`; integrated in `Gatekeeper` pipeline | 7 unit tests in `tests/test_token_bucket.py` | PASS |
| 29 | DOS detector — burst/repeated-game-id detection with circuit breaker | `DosDetector` at `agent/gmail/dos_detector.py:8`; `CircuitBreaker` at `agent/gmail/circuit_breaker.py`; both imported and used in `Gatekeeper.__init__` | `tests/test_dos_detector.py`; `tests/test_circuit_breaker.py` | PASS |
| 30 | Send-only Gmail — OAuth scope limited to `gmail.send` | `docs/GMAIL_REPORTING_RUNBOOK.md` specifies `gmail.send` scope; `agent/gmail/gatekeeper.py` uses send-only API path; `RECIPIENT` constant enforces single destination | Runbook documented; real OAuth credentials require external setup | EXTERNAL_PENDING |

## Rules 31–45: League and Submission

| # | Rule | Production Code | Test Evidence | Status |
|---|------|----------------|---------------|--------|
| 31 | Minimum different groups — ledger enforces at least 2 distinct opponents | `MIN_DIFFERENT_GROUPS = 2` in `agent/step0/league_ledger.py`; `validate_before_append()` raises `LeagueLedgerError` on violation; `has_minimum_opponents()` check | `tests/test_league_ledger.py` | EXTERNAL_PENDING — code enforces; real matches against different groups required |
| 32 | Automatic Gmail report — Gatekeeper sends result report automatically after game series | `Gatekeeper` at `agent/gmail/gatekeeper.py`; `RECIPIENT = "rmisegal+uoh26finalgame@gmail.com"` at line 11; `ResultAgreement` JSON serialized and sent | `tests/test_gmail_gatekeeper.py` (fake-service tests) | EXTERNAL_PENDING — real Gmail send requires OAuth credentials |
| 33 | Valid JSON report — report body is valid JSON; schema validated before send | `ResultAgreement.canonical_bytes()` produces valid JSON; `Gatekeeper._validate_body()` checks `body.startswith('{')` | `tests/test_result_consensus.py`; `tests/test_gmail_gatekeeper.py` | PASS |
| 34 | No free-text final report — body must start with `{` (JSON) or GatekeeperError raised | `Gatekeeper._validate_body()` raises `GatekeeperError` if body does not start with `{` | `tests/test_gmail_gatekeeper.py::test_plain_text_rejected` | PASS |
| 35 | Bilateral result agreement and dual sends — both peers independently sign and send the result | `SignedResultAgreement` and `verify_bilateral_consensus()` at `agent/audit/result_consensus.py`; `Gatekeeper.send()` called from `peer_runtime.py:run_game()` for counted mode after audit passes (v8 Phase 3); `AgentOrchestrator.send_report_via_gatekeeper()` at line 455; Gmail send wired in terminal state | `tests/test_phase3_audit_reporting_v8.py::TestGatekeeperWiring`; real Gmail credentials EXTERNAL_PENDING | PASS — Gatekeeper wired into production path; real OAuth credentials and partner report are EXTERNAL_PENDING |
| 36 | Mutual comprehensive audit — bilateral AuditSummary with consensus verification | `AuditSummary` + `SignedAuditSummary` + `create_signed_audit_summary()` at `agent/audit/audit_summary.py`; `do_final_audit()` now creates and signs `AuditSummary`, parses opponent's signed summary, calls `verify_audit_summary()` (`peer_runtime_audit.py` v8); passive side `handle_passive_final_audit()` returns nonces + `SignedAuditSummary` | `tests/test_phase3_audit_reporting_v8.py::TestBilateralAuditSummary` (4 tests); `tests/test_mcp_and_peer_agents.py::test_on_action_final_audit` | PASS — bilateral AuditSummary exchange implemented; full result consensus exchange EXTERNAL_PENDING for live match |
| 37 | Accurate counted-match declaration — `previous_counted_matches` in PeerDeclaration; ledger enforces | `PeerDeclaration.previous_counted_matches` at `declaration.py:68`; `LeagueLedger` tracks and validates; populated in `build_step0_declaration()` | `tests/test_step0_declarations.py`; `tests/test_league_ledger.py` | PASS |
| 38 | False declaration disqualification — `validate_for_counted_mode()` detects placeholder/false values | `validate_for_counted_mode()` at `agent/step0/validator.py`; checks git_sha, group_id (8 chars, not placeholder), model_sha256; called during counted startup via `orchestrator.validate_counted_declaration()` | `tests/test_validator.py`; `tests/test_production_lifecycle_integration.py` | PASS |
| 39 | No secrets in repo — credentials.json/token.json excluded; CI secret scan passes | `.gitignore` lines 9–13: `credentials.json`, `token.json`, `secrets/`, `*.credentials.json`, `*.token.json` | CI pipeline secret scan; `.gitignore` verified | PASS |
| 40 | Credentials in .gitignore — all credential patterns explicitly listed | `.gitignore` explicitly lists all credential file patterns | `.gitignore` content verified | PASS |
| 41 | Documented Git tag — v3.0-code-ready tag created at Phase 5 v7 completion | Tag `v3.0-code-ready` on main branch (thief: c0b6d90, cop: 1ad6fbf) | `git tag` output; `docs/RELEASE_CHECKLIST.md` | PASS |
| 42 | Academic README — README contains full academic content per spec | `README.md` at repo root; rewritten with architecture, protocol, installation, configuration, testing, companion-repo cross-link sections | `README.md` at repo root | PASS |
| 43 | Moodle unchanged-layout PDF — submission PDF with original layout | `docs/RELEASE_CHECKLIST.md` documents PDF requirement | PDF generation and Moodle upload require external action | EXTERNAL_PENDING |
| 44 | Individual Moodle submission — each team member submits separately | Noted in `docs/RELEASE_CHECKLIST.md` | Each member must submit individually on Moodle | EXTERNAL_PENDING |
| 45 | Unique eight-character group ID — validator enforces exactly 8 chars; not placeholder | `validate_for_counted_mode()`: `len(decl.group_id) != 8` → error; `PLACEHOLDER_GROUP_IDS` set checked; real ID assigned by course | `tests/test_validator.py` | EXTERNAL_PENDING — validator enforces; real group ID assigned by course |

## Rules 46–55: Cross-Checked Requirements

| # | Rule | Production Code | Test Evidence | Status |
|---|------|----------------|---------------|--------|
| 46 | Barrier-on-thief capture — placing a barrier on the thief's cell is a legal cop win | `apply_place_action()` in `agent/rl/env_helpers.py`; `check_game_status()` detects barrier-on-thief capture via positional equality | `tests/test_rl_tools_reports.py::test_apply_place_action_on_thief_is_capture`; `TestBarrierOnThiefCapture` (4 tests) | PASS |
| 47 | Trapped thief capture — thief with no orthogonal escape (STAY excluded) is cop win | `Board.has_orthogonal_escape()` in `agent/board.py`; STAY excluded from escape check at `domain/transition.py:270`; `check_game_status()` uses it | `tests/test_rl_tools_reports.py::test_thief_trapped_when_only_stay_available`; `TestTrappedThiefSemantics` (7 tests) | PASS |
| 48 | Scoring table — fixed scoring vector: capture\_cop=20, capture\_thief=5, survival\_cop=5, survival\_thief=10, diversity=10 | `FieldKind.FIXED` entries in `_FIELD_SPECS` at `agent/config/canonical_config.py:47–50`; enforced on every config load | `tests/test_canonical_config.py`; `tests/test_config_conformance.py::test_capture_cop_must_be_20` | PASS |
| 49 | Two repositories / cross-links — cop and thief repos cross-reference each other | `README.md` in both repos contains companion-repo link section; mirrored code structure | `README.md` in both repos verified | PASS |
| 50 | README/config/PRD/PLAN/TODO — all required files present | `README.md`, `PRD.md`, `PLAN.md`, `TODO.md` at repo root; `game_config.toml` in config dir | `ls` of repo root; all files confirmed | PASS |
| 51 | Correct report address — RECIPIENT = "rmisegal+uoh26finalgame@gmail.com" | `RECIPIENT = "rmisegal+uoh26finalgame@gmail.com"` at `agent/gmail/gatekeeper.py:11` | Grep confirmed exact string match | PASS |
| 52 | One counted match per opponent — LeagueLedger.validate_before_append enforces | `validate_before_append()` at `agent/step0/league_ledger.py:82`; raises `LeagueLedgerError` if same opponent already present | `tests/test_league_ledger.py` (duplicate-opponent rejection test) | PASS |
| 53 | Git SHA in Step-0 — PeerDeclaration.git_sha; validate_for_counted_mode rejects placeholder | `PeerDeclaration.git_sha` at `declaration.py:30`; `build_step0_declaration()` calls `git rev-parse HEAD`; `validate_for_counted_mode()` rejects empty/placeholder/unknown | `tests/test_validator.py`; `tests/test_step0_declarations.py::test_validate_counted_mode_rejects_*` | PASS |
| 54 | Token totals in final JSON — ResultAgreement.token_totals and AuditSummary.token_totals fields present | `ResultAgreement.token_totals: dict` at `audit/result_consensus.py:28`; `AuditSummary.token_totals: dict` at `audit/audit_summary.py:25`; both schema fields populated | `tests/test_audit_summary.py`; `tests/test_result_consensus.py` | PASS |
| 55 | Self-grade code quality only — self-grading based on code quality, not external match outcomes | Noted in `docs/RELEASE_CHECKLIST.md`; self-grading rubric in PRD | Acknowledged in release documentation | EXTERNAL_PENDING |

---

## Summary

| Status | Count | Rule Numbers |
|--------|------:|-------------|
| PASS | 45 | 1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 13, 14, 15, 16, 17, 18, 19, 21, 22, 23, 24, 26, 27, 28, 29, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 46, 47, 48, 49, 50, 51, 52, 53, 54 |
| EXTERNAL_PENDING | 10 | 10, 20, 25, 30, 31, 32, 43, 44, 45, 55 |
| FAIL | 0 | — |

**Total: 55 rules. PASS=45, EXTERNAL_PENDING=10, FAIL=0.**

> **v8 changes from v7:**
> - Rule 25: FAIL → EXTERNAL_PENDING (v8 spec: "Rule 25 is RECOMMENDED, not mandatory")
> - Rule 35: FAIL → PASS (Gatekeeper.send() wired in peer_runtime.py terminal state; v8 Phase 3)
> - Rule 36: FAIL → PASS (bilateral SignedAuditSummary exchange in do_final_audit(); v8 Phase 3)
> - PASS count: 43 → 45. EXTERNAL_PENDING: 9 → 10. FAIL: 3 → 0.

---

**v7 Phase 6 changes from Phase 5 v7 / v6 FINAL report (2026-08-04):**
- Rule 35: EXTERNAL_PENDING → FAIL — `verify_bilateral_consensus()` exists in `result_consensus.py` but is never called from `peer_runtime.py`; Gatekeeper never invoked at game end
- Rule 36: PASS → FAIL — `do_final_audit()` in `peer_runtime_audit.py` runs the hash audit but never instantiates `AuditSummary`; bilateral consensus check absent from production path
- Rule 41: Updated tag reference from `v2.0-submission` to `v3.0-code-ready`
- PASS count: 44 (Phase 5 v7) → 43 (rule 36 demoted to FAIL)
- EXTERNAL_PENDING count: 10 (Phase 5 v7) → 9 (rule 35 demoted from EXTERNAL_PENDING to FAIL)
- FAIL count: 1 (Phase 5 v7) → 3 (rules 35 and 36 added)

> **Rules 35 and 36 — What's missing:** Both `AuditSummary` and `verify_bilateral_consensus()` are fully implemented as standalone classes. The production gap is in `agent/peer_runtime_audit.py::do_final_audit()`: it runs the nonce-audit but returns a plain `(bool, dict)` tuple instead of constructing an `AuditSummary`, and `peer_runtime.py` never calls `Gatekeeper.send()` after the audit. A human developer must: (1) instantiate `AuditSummary` inside `do_final_audit` from the audit result, (2) exchange `SignedResultAgreement` with the opponent, (3) call `verify_bilateral_consensus()`, and (4) invoke `Gatekeeper.send()` with the JSON body.
