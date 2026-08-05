# TODO — vibecode-cop Development Checklist

Last updated: 2026-08-05

---

## Codex Stage B/C — ✅ Complete

Verified source commit: `b9f672381fb3c456a0a6fdb3f99a113750333548`

Final readiness evidence commit: `037f5b675a65999586dff85e2b6599dcdb9cb667`

- [x] Fail-closed counted CLI and sole AgentOrchestrator composition.
- [x] Signed Step-0, adaptive profile, canonical turns, audit/result, reciprocal
  ledgers, token totals, and independent Gatekeeper paths.
- [x] Checksum-bound recurrent cop champion and paired tournament promotion.
- [x] Strict verifier: 11/11 code gates PASS; no failures or accepted skips.
- [x] Full pytest: cop 1,467; thief 1,340; branch coverage 85.8130% / 85.1753%.
- [x] Real two-process six-gamelet series `series_20260805_064801_ea4d7c38`.
- [x] Final reports, 55-rule trace, manifests, score JSON, ExecPlan, and ledger.
- [x] Cost ledger, sensitivity notebook, and counted-lifecycle architecture asset.

## Historical completed phases

### Phase 1: Board + Rules Engine ✅
- [x] 7×7 board, orthogonal movement, barriers (`agent/board.py`)
- [x] RulesEngine: capture, survival, TECHNICAL_LOSS, GameOutcome (`agent/rules_engine.py`)
- [x] `config/game.json` — shared game parameters (barriers, max_moves, scoring)
- [x] `agent/config/shared_config.py` — load, validate, SHA-256

### Phase 2: MCP Protocol ✅
- [x] SHA-256 commit-reveal protocol (`agent/mcp/crypto.py`)
- [x] HMAC-SHA256 message authentication
- [x] `gamelet` field in commitment payload (prevents cross-gamelet replay attacks)
- [x] FastMCP server and client (`agent/mcp/server.py`, `agent/mcp/client.py`)
- [x] Message schemas (`agent/mcp/messages.py`, `agent/mcp/messages_game.py`)
- [x] Structured game log writer (`agent/mcp/log.py`)
- [x] 25 MCP tests passing

### Phase 3: LLM Crew + Orchestration ✅
- [x] CrewAI GameManager + StrategyAgent crew (`agent/orchestrator_crew.py`)
- [x] Orchestrator phase management (`agent/orchestrator_phase.py`)
- [x] Game-level orchestration (`agent/orchestrator_game.py`)
- [x] LLM fallback for development/warmup cold start; counted mode requires RL

### Phase 4: P2P Runtime ✅
- [x] `PeerRuntime` — no central judge; cop verifies thief locally (`agent/peer_runtime.py`)
- [x] `PeerTurnLoop` — full commit→send→receive→reveal→verify→apply per turn
- [x] `PeerAudit` — runs final audit from local disk files only
- [x] `cop/__init__.py` and `cop/__main__.py` — cop entry point
- [x] TECHNICAL_LOSS on commitment mismatch

### Phase 5: Six-Gamelet Series ✅
- [x] `GameSeries.run_series(n_gamelets=6)` (`agent/game_series.py`)
- [x] Gamelet labels g01–g06
- [x] Score accumulation (cop_total, thief_total)
- [x] Tie detection
- [x] `result_{series_id}_series.json` written

### Phase 6: RL Strategy Training ✅
- [x] Q-table cop strategy trained (80k episodes, saved to `models/cop_qtable.npy`)
- [x] DQN cop strategy retrained (40k episodes, `models/cop_dqn.pt`)
- [x] GreedyCopStrategy: minimize Chebyshev distance to scent peak
- [x] ComboCopStrategy: hybrid RL + greedy
- [x] Strategy tournament: 500 games per matchup, round-robin leaderboard
- [x] Cop observation uses scent field (never true thief position) — AC4 compliant

### Phase 7: Reports + Gmail ✅
- [x] `ReportBundleBuilder` raises `FileNotFoundError` instead of creating stubs
- [x] `GameRunner._copy_files_to_agent_dirs()` copies real files to agent dirs
- [x] `declaration_{game_id}.json` includes: hardware, LLM model, git commit, gamelet, config SHA-256
- [x] Config file naming uses `g{NN}` gamelet number
- [x] Gmail OAuth 2.0 with `gmail.send` scope only
- [x] GmailGatekeeper: max 10 sends/day, idempotency per game_id
- [x] Modes: `disabled | dry_run | draft | send`

### Phase 8: Compliance Fixes ✅
- [x] Scoring loaded from `config/game.json` at runtime (not hardcoded)
- [x] `group_name: "vibecode"` added to `config/game.json`
- [x] Watchdog timeout added to `peer_turn_loop.py`
- [x] `scripts/replay_viewer.py` CLI for offline log audit
- [x] TECHNICAL_LOSS forced when `audit_ok=False`
- [x] Fixed values enforced (diagonal_moves, pheromones)
- [x] Minimum values enforced (max_barriers, max_moves)
- [x] `[reports]` section forbidden in shared config

### Phase 9: Historical Test Baseline ✅
- [x] `tests/test_shared_config_contract.py` (19 tests) — SHA-256 config lock
- [x] `tests/test_peer_runtime_no_central_judge.py` (32 tests) — P2P invariants
- [x] `tests/test_replay_audit.py` (8 tests) — tamper detection
- [x] `tests/test_thief_rl_no_true_cop_position.py` (8 tests) — hidden info (cop observation verified)
- [x] `tests/test_game_series_six_gamelets.py` (7 tests) — series scoring
- [x] `tests/test_network_timeout_technical_loss.py` (3 tests) — watchdog
- [x] `tests/test_commitment_mismatch_technical_loss.py` (2 tests)
- [x] `tests/test_commit_payload_required_fields.py` (5 tests)
- [x] `tests/test_declaration_required_fields.py` (7 tests)
- [x] `tests/test_live_gui_role_filtering.py` (5 tests)
- [x] `tests/test_report_no_stub_creation.py` (3 tests)
- [x] `tests/test_report_uses_authoritative_files.py` (1 test)
- [x] `tests/test_gmail_config_driven.py`
- [x] `tests/test_compliance.py`
- [x] Superseded final totals: cop 1,467; thief 1,340; zero skipped
- [x] Final branch coverage: cop 85.8130%; thief 85.1753%

### Phase 10: Docs + Submission ✅
- [x] `README.md` — quick start, architecture, runbook
- [x] `PRD.md` — cop-specific product requirements (v1.2)
- [x] `PLAN.md` — C4 model, MCP sequence diagrams, strategy flowchart
- [x] `TODO.md` — this file
- [x] `docs/PRD_agent.md`, `docs/PRD_rl.md`, `docs/rules.md`
- [x] `docs/cost.md` and `notebooks/cost_sensitivity.ipynb`
- [x] `assets/counted_lifecycle.svg` architecture diagram
- [x] `scripts/replay_viewer.py` — offline audit CLI
- [x] `config.toml.example` and `.env.example` (no secrets committed)
- [x] `pyproject.toml` with all dependencies pinned

---

## Open Items

- [ ] **Public tunnel match**: Not yet tested against an opponent over a public tunnel (ngrok/cloudflare). The P2P runtime is implemented and tested locally; live cross-network match is pending.
- [x] **Jupyter notebook**: Cost and sensitivity analysis is tracked.
- [x] **Architecture diagram**: Counted lifecycle SVG is tracked.
- [ ] **Gmail live send**: Integration tested via `dry_run`/`draft` modes. A live `send` requires active `credentials.json`; documented in README runbook.
- [ ] **Course identity and submission**: real group ID, official PDF/screenshots,
  individual Moodle submissions, and pushed final tags remain EXTERNAL_PENDING.
