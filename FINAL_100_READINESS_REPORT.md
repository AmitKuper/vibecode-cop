# Final 100-Readiness Report — v8 Updated Assessment

## Release Information

| Field | Value |
|-------|-------|
| thief SHA | `caa49f7` (v8 Phase 5 complete) |
| cop SHA | `7ab1b11` (v8 Phase 5 complete) |
| Date | 2026-08-04 |
| Phase pack | v8 (Phases 1–6 v8 complete) |
| Previous release | v7 (cop `1ad6fbf`, thief `c0b6d90`, tag `v3.0-code-ready`) |
| Package version | 3.0.0 |

## Score Estimate (Honest)

| Area | v7 Estimate | v8 Honest Estimate | v8 Notes |
|------|------------:|--------------------|----------|
| Requirements and design fidelity | 82 | 87 | Rules 35/36 fixed; Rule 25 reclassified as RECOMMENDED |
| Core game mechanics | 90 | 90 | P0-2 barrier divergence fixed; domain engine canonical |
| Production P2P protocol | 88 | 90 | P0-1 counted mode propagation fixed |
| Cryptographic integrity and audit | 78 | 86 | Bilateral AuditSummary exchange now wired (Rule 36 PASS) |
| Competitive RL readiness | 15 | 15 | Still EXTERNAL_PENDING; placeholder weights |
| Reliability, reporting, Gmail | 72 | 82 | Gatekeeper wired in terminal state (Rule 35 PASS) |
| Hidden-coord / local truth | 75 | 90 | RL observation fixed; no cop position reaches thief actor |
| Language strategy | 78 | 85 | Symmetric policy; step propagation fixed |
| MCP adaptability | 82 | 82 | Unchanged |
| Documentation and release evidence | 88 | 90 | README fixed (--cop-url→--thief-url); version synced 3.0.0 |
| **Estimated weighted overall** | **~78** | **~84** | All code-verifiable FAILs resolved |

> **v8 floor:** Cannot reach 90+ without: (1) real GPU RL training, (2) real matches + Gmail sends against 2+ groups, (3) Moodle submission, (4) 8-char group ID.

## Quality Gate Evidence

| Gate | thief (caa49f7) | cop (7ab1b11) |
|------|-----------------|---------------|
| Test count | **1143 passed**, 2 skipped, 0 failed | **1189 passed**, 2 skipped, 0 failed |
| Branch coverage | ≥85% | ≥85% |
| Ruff violations | 0 | 0 |
| Secret scan | clean | clean |
| Package version | 3.0.0 | 3.0.0 |

## 55-Rule Summary (v8 Honest)

| Status | Count | Rule Numbers |
|--------|------:|-------------|
| PASS | 45 | 1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 13, 14, 15, 16, 17, 18, 19, 21, 22, 23, 24, 26, 27, 28, 29, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 46, 47, 48, 49, 50, 51, 52, 53, 54 |
| EXTERNAL_PENDING | 10 | 10, 20, 25, 30, 31, 32, 43, 44, 45, 55 |
| FAIL | 0 | — |

> v8 changes: Rule 25 FAIL→EXTERNAL_PENDING (RECOMMENDED per spec); Rules 35, 36 FAIL→PASS (wired in v8 Phase 3).

Full traceability: [docs/REQUIREMENTS_TRACEABILITY.md](docs/REQUIREMENTS_TRACEABILITY.md)

## What v7 Improved vs v6

### Production Wiring Verified (v7 grep evidence)

All of the following were **verified by grep against the actual production path**:

| v7 Wire | Production File | Line |
|---------|----------------|------|
| `update_scent_and_belief()` | `agent/peer_turn_loop.py` | 178 |
| `publish_live_view()` | `agent/peer_turn_loop.py` | 198 |
| `record_step_evidence()` | `agent/peer_turn_loop.py` | 215 |
| `start_watchdog()` | `agent/peer_runtime.py` | 152 |
| `validate_counted_declaration()` | `agent/peer_runtime.py` | 248 |
| `build_step0_declaration()` | `agent/peer_runtime.py` | 247 |
| `generate_strategic_hint()` | `agent/peer_turn_loop.py` | 75 |
| `select_move_heuristic()` | `agent/peer_turn_loop.py` | 64 |
| `emit_heartbeat()` | `agent/peer_turn_loop.py` | 264 |
| `build_local_observation()` | `agent/peer_turn_helpers.py` | 236 (no hidden coords) |

### v8 Fixes vs v7

**Rule 35 (bilateral send) — now PASS (v8 Phase 3):**
- `Gatekeeper.send()` wired into `peer_runtime.py::run_game()` terminal state for counted mode
- `AgentOrchestrator.send_report_via_gatekeeper()` called after audit passes
- Real Gmail credentials are EXTERNAL_PENDING; structure is complete

**Rule 36 (mutual audit) — now PASS (v8 Phase 3):**
- `do_final_audit()` in `peer_runtime_audit.py` now creates and signs `AuditSummary` using ephemeral Ed25519 key
- Passive side `handle_passive_final_audit()` runs its own audit, creates signed summary, returns both nonces + summary
- Active side verifies opponent's `SignedAuditSummary` via `verify_audit_summary()`
- Bilateral consensus verified at protocol level

**Rule 25 (RL) — reclassified EXTERNAL_PENDING (per v8 spec):**
- v8 spec: "Rule 25 is RECOMMENDED, not mandatory. Do not count an untrained model as a formal Rule-25 violation."
- Real training requires GPU time — infrastructure is complete

**P0-1 (v8 Phase 1) — FIXED:**
- `RuntimeMode.COUNTED` now correctly propagated from CLI → `run_series.py` → `PeerRuntime` → `AgentOrchestrator`
- Was: `PeerRuntime` always defaulted to `counted_mode=False`

**P0-2 (v8 Phase 1) — FIXED:**
- Cop `PLACE_*` barrier actions now applied by canonical `apply_joint_action()` on the active side
- Was: legacy `RulesEngine` converted PLACE_* to STAY silently, causing active/passive board divergence

**Hidden coordinate RL leak (v8 Phase 2) — FIXED:**
- `thief_observation()` channel 1 replaced from cop 1-hot to cop scent field (historical trail)
- `select_move()` RL path removed (`_build_observation` with grid_state exposed both positions)
- `build_local_observation()` is now the sole actor input path

**Language policy step constant (v8 Phase 4) — FIXED:**
- `generate_strategic_hint()` now accepts and passes real `step` parameter
- Passive side uses `NaturalLanguagePolicy` instead of always-truth template

## Phases Completed

| Phase | Description | thief SHA | cop SHA |
|-------|-------------|-----------|---------|
| Phase 1 v7 | RuntimeMode enum, AgentOrchestrator composition root, fix counted CLI | `991e398` | `28feaa7` |
| Phase 2 v7 | Canonical domain path, symmetric scent wired, hidden-coord removed | `b4dba23` | `b5de5b1` |
| Phase 3 v7 | Wire Step-0, StepJournal, Watchdog, LeagueLedger into production lifecycle | `1b5af13` | `07736ed` |
| Phase 4 v7 | NaturalLanguagePolicy with DeceptionIntent, belief-driven heuristic, counted model validation | `abc300e` | `7fddd0d` |
| Phase 5 v7 | SafeLiveView wired to production, GameProtocolPort, accurate README, v3.0-code-ready | `c0b6d90` | `1ad6fbf` |
| Phase 1 v8 | Fix P0-1 (counted_mode not passed to PeerRuntime) and P0-2 (PLACE_* barrier divergence) | `9a7667e` | `4c11016` |
| Phase 2 v8 | Fix hidden-coord RL leak, config authority, public/private state commitments | `0b2d959` | `3168f60` |
| Phase 3 v8 | Bilateral AuditSummary exchange, Gatekeeper wired in terminal state, LeagueLedger wired | `5f62111` | `ac8cbdc` |
| Phase 4 v8 | Symmetric language policy, step propagation fix | `5f62111` | `ac8cbdc` |
| Phase 5 v8 | Version sync 3.0.0, README --cop-url fix, manifest update | `caa49f7` | `7ab1b11` |
| Phase 6 v8 | Updated 55-rule RTM (PASS=45, EP=10, FAIL=0), FINAL_100_READINESS_REPORT | *(this commit)* | *(this commit)* |

## Key Remaining Gaps — Priority Order for a Human Developer

### Priority 1: Real Opponents and Gmail Credentials (Rules 31, 32)

- Obtain Gmail OAuth credentials with `gmail.send` scope only
- Run `uv run python -m agent.gmail.auth` to generate `token.json`
- Arrange counted series against at least 2 different opponent groups

### Priority 3: RL Training (Rule 25)

- Run `uv run python -m agent.rl.train_cli --mode selfplay --steps 1000000` on GPU hardware
- Update `models/MANIFEST.json` with real `sha256`, `training_steps`, `evaluation_win_rate`

### Priority 4: External Course Actions (Rules 43, 44, 45, 55)

- Obtain 8-character group ID from course; update `game_config.toml` in both repos
- Fill in Moodle PDF with original layout unchanged
- Each team member submits individually to Moodle

## External Action Checklist

See [FINAL_EXTERNAL_ACTION_CHECKLIST.md](FINAL_EXTERNAL_ACTION_CHECKLIST.md)
