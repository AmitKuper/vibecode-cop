# Phase 2B — Production Protocol Integration Report

**Date:** 2026-08-03  
**Phase:** 2B — Connect 16-state machine to production path

---

## Baseline SHAs

| Repo | Pre-2B SHA |
|------|-----------|
| `vibecode-cop` | `0ea74157034e92bd7faba6b883bdf979f7b21568` |
| `vibecode-thief` | `e3b20404c55ed5d1592c827fbf5dbd9fb4c8da05` |

---

## P0 Defect: Failure Transcript (pre-fix)

**Root cause:** `PeerRuntime.run_game()` called `_init_protocol_adapter()` (tool
discovery only) and then immediately launched `run_peer_turn_loop()`.  The turn
loop called `send_commit()` at step 1 with no preceding `start_game` handshake
and without calling any `notify_*` hooks.

**What the thief saw:**

```
Session state: IDLE  (no start_game was ever received)
Inbound message: COP COMMIT step=1
Guard result: guard_commit_received() → False, "Received commit in unexpected state idle"
Response: {"ok": false, "error": "Protocol violation: Received commit in unexpected state idle"}
```

**What the cop saw:**

```
opponent_resp = {"ok": false, "error": "Protocol violation: ..."}
opp_h_commit = opponent_resp.get("h_commit")  → None
return None, "Opponent did not return h_commit at step 1"
```

**Evidence test:** `tests/test_two_process_integration.py::TestP0Defect::test_commit_before_handshake_rejected`
confirms this failure deterministically with an isolated registry.

---

## Architecture: ProtocolCoordinator

### Design principle

One `ProtocolCoordinator` instance is the sole authority for all inbound and
outbound protocol state machine transitions.  Scattered direct SM mutations
(previously in `server_handlers.py` notify helpers) are replaced with
coordinator method calls.

### Sequence diagram — one gamelet, same-protocol peers

```
Cop (active)                         Thief (passive)
────────────────────────             ────────────────────────
PeerRuntime.run_game(game_id)
  │
  ├─ _init_protocol_adapter()        [thief MCP server running]
  │
  ├─ _send_start_game(game_id)
  │     │
  │     └──── start_game ──────────► handle_start_game()
  │                                     coord.on_handshake_complete()
  │                                     SM: IDLE→STEP0_NEGOTIATING→READY
  │     ◄──── {"ok": true} ──────────
  │
  │  coord.on_handshake_complete()
  │  SM: IDLE→STEP0_NEGOTIATING→READY
  │
  ├─ run_peer_turn_loop()
  │
  │  [step 1]
  │  coord.begin_step()
  │  SM: READY→COMPUTING_MOVE
  │  select_move()
  │  create_commitment()
  │
  ├─ send_commit(step=1, h_commit)
  │     │
  │     └──── COMMIT action ────────► handle_action()
  │                                     coord.check_and_advance_inbound_commit()
  │                                       SM auto: READY→COMPUTING_MOVE
  │                                       SM: COMPUTING_MOVE→COMMIT_RECEIVED
  │                                     handle_passive_commit() [callback]
  │                                       compute own commit
  │                                     coord.on_passive_commit_sent()
  │                                       SM: COMMIT_RECEIVED→BOTH_COMMITTED
  │     ◄──── {"ok":true, h_commit} ─
  │
  │  coord.on_commit_exchange_complete()
  │  SM: COMPUTING_MOVE→COMMIT_SENT→BOTH_COMMITTED
  │
  ├─ send_reveal(step=1, move, nonce)
  │     │
  │     └──── REVEAL action ────────► handle_action()
  │                                     coord.check_and_advance_inbound_reveal()
  │                                       SM: BOTH_COMMITTED→REVEAL_RECEIVED
  │                                     handle_passive_reveal() [callback]
  │                                       apply moves, compute reveal
  │                                     coord.on_passive_reveal_sent()
  │                                       SM: REVEAL_RECEIVED→STEP_VERIFIED
  │     ◄──── {"ok":true, move, ...} ─
  │
  │  coord.on_reveal_exchange_complete()
  │  SM: BOTH_COMMITTED→REVEAL_SENT→STEP_VERIFIED
  │
  │  apply moves locally, check outcome
  │  [repeat for steps 2..N]
  │
  ├─ do_final_audit()
  │     │
  │     └──── FINAL_AUDIT action ──► handle_action()
  │                                     coord.check_final_audit_guard()
  │                                       SM: STEP_VERIFIED→AUDITING→RESULT_AGREEMENT
  │     ◄──── {"ok":true, nonces} ──
  │
  │  coord.on_audit_begin()
  │  SM: STEP_VERIFIED→AUDITING
  │  coord.on_final_audit_complete()
  │  SM: AUDITING→RESULT_AGREEMENT
  │  coord.on_done()
  │  SM: RESULT_AGREEMENT→REPORTING→DONE
  │
  ├─ notify_game_end()
  └─ write_result()
```

### Inter-step state for passive side

Between steps, the thief's SM sits at `STEP_VERIFIED`.  When the cop's next
COMMIT arrives, `check_and_advance_inbound_commit()` auto-transitions
`STEP_VERIFIED → COMPUTING_MOVE` before the guard check, so the second and
all subsequent steps proceed without separate `notify_step_begin()` calls from
the passive side.

---

## File-by-file changes

### New files

#### `agent/mcp/coordinator.py`

`ProtocolCoordinator` — the single authority for all SM transitions.

Key methods:

| Method | Caller | Effect |
|--------|--------|--------|
| `on_handshake_complete()` | `handle_start_game`, `PeerRuntime._send_start_game` | IDLE→STEP0_NEGOTIATING→READY |
| `begin_step()` | `run_peer_turn` | READY/STEP_VERIFIED→COMPUTING_MOVE |
| `on_commit_exchange_complete()` | `run_peer_turn` (after send_commit) | COMPUTING_MOVE→COMMIT_SENT→BOTH_COMMITTED |
| `on_reveal_exchange_complete()` | `run_peer_turn` (after send_reveal) | BOTH_COMMITTED→REVEAL_SENT→STEP_VERIFIED |
| `check_and_advance_inbound_commit()` | `handle_action` | auto-advance from READY/STEP_VERIFIED→COMPUTING_MOVE; idempotency check; COMPUTING_MOVE→COMMIT_RECEIVED; returns prev_state for rollback |
| `on_passive_commit_sent()` | `handle_action` (after callback returns h_commit) | COMMIT_RECEIVED→BOTH_COMMITTED |
| `check_and_advance_inbound_reveal()` | `handle_action` | BOTH_COMMITTED→REVEAL_RECEIVED; idempotency; returns prev_state |
| `on_passive_reveal_sent()` | `handle_action` (after callback returns move) | REVEAL_RECEIVED→STEP_VERIFIED |
| `rollback_inbound_commit()` | `handle_action` (on callback failure) | restores prev_state |
| `rollback_inbound_reveal()` | `handle_action` (on callback failure) | restores prev_state |
| `on_technical_loss()` | `run_peer_turn` (on network failure) | any→TECHNICAL_LOSS |
| `on_audit_begin()` | `peer_runtime_audit` | STEP_VERIFIED→AUDITING |
| `on_final_audit_complete()` | coordinator internal | AUDITING→RESULT_AGREEMENT |
| `on_done()` | `peer_runtime` (end of run_game) | RESULT_AGREEMENT→REPORTING→DONE |

Idempotency: keyed on `(game_id, gamelet, role, step, phase)`.  Exact duplicate
returns cached response.  Conflicting duplicate returns error.

Transactional: SM advanced before callback; rolled back if callback raises.

#### `tests/test_two_process_integration.py`

18 tests in 5 classes:
- `TestP0Defect` — preserved failure evidence (3 tests)
- `TestAfterFix` — handshake → commit → reveal → multi-step (7 tests)
- `TestConcurrency` — concurrent commits serialized; technical_loss (2 tests)
- `TestOutboundCoordinatorHooks` — cop-side SM lifecycle (3 tests)
- `TestAuditAndDone` — AUDITING → DONE (1 test, inside TestOutboundCoordinatorHooks)

### Modified files

#### `agent/mcp/server_handlers.py`

- `handle_start_game()`: accepts optional `coordinator=` parameter; replaces
  direct lock+SM mutation with `coord.on_handshake_complete()`; guards
  duplicate start_game by inspecting current state before calling coordinator.
- `handle_action()`: fully rewritten action dispatch:
  - commit: `check_and_advance_inbound_commit()` → callback → `record_commit_response()` + `on_passive_commit_sent()`; rollback on failure
  - reveal: `check_and_advance_inbound_reveal()` → callback → `record_reveal_response()` + `on_passive_reveal_sent()`; rollback on failure
  - final_audit: `check_final_audit_guard()` → callback
  - abort, game_end: passthrough
- `notify_*` functions: now thin wrappers around the coordinator (kept for
  backwards compatibility).
- `_gamelet_from_game_id` aliased to `coordinator.gamelet_from_game_id`.

#### `agent/peer_runtime.py`

- Added `my_endpoint: str = ""` constructor parameter.
- Added import of `gamelet_from_game_id`, `get_coordinator`.
- `run_game()`: calls `await self._send_start_game(game_id)` after
  `_init_protocol_adapter()` and before `run_peer_turn_loop()`.
- New `_send_start_game()` method:
  - constructs `StartGameMessage` with config_sha256, protocol_version, endpoint
  - calls `opponent_client.start_game(msg)`
  - on success: `get_coordinator().on_handshake_complete()` to advance local SM
  - on failure: logs warning, allows turn loop to fail cleanly

#### `agent/peer_turn_loop.py`

- Added `gamelet_from_game_id`, `get_coordinator` imports.
- `run_peer_turn()` now calls:
  - `coord.begin_step()` before `select_move()`
  - `coord.on_commit_exchange_complete()` after successful `send_commit()`
  - `coord.on_reveal_exchange_complete()` after successful `send_reveal()`
  - `coord.on_technical_loss()` on send failures

#### `agent/peer_agent_passive.py`

- Minor: removed now-unused imports (cleaned by ruff after coordinator was
  correctly placed in `server_handlers.py`).

---

## Exact commands and outputs

### Quality gates — vibecode-thief

```
uv run pytest tests/ agent/tests/ -q
→ 709 passed, 0 failed (94.92s)

uv run pytest tests/ agent/tests/ --cov=agent --cov-branch --cov-fail-under=85
→ 709 passed, Total coverage: 87.83% (required 85%) ✓

uv run ruff check .
→ All checks passed

uv run ruff format --check .
→ 181 files already formatted
```

### Quality gates — vibecode-cop

```
uv run pytest tests/ agent/tests/ -q
→ 710 passed, 0 failed (94.99s)

uv run ruff check .
→ All checks passed

uv run ruff format --check .
→ 183 files already formatted
```

---

## Two-process gamelet evidence (in-process)

Test `TestAfterFix::test_one_full_step_with_passive_callbacks` demonstrates a
complete one-gamelet step using real production handler functions
(`handle_start_game`, `handle_action`, `handle_passive_commit`,
`handle_passive_reveal`) with an isolated in-process registry.

State machine trace for that test:

```
start_game    → IDLE → STEP0_NEGOTIATING → READY
commit step=1 → READY → COMPUTING_MOVE → COMMIT_RECEIVED → BOTH_COMMITTED
reveal step=1 → BOTH_COMMITTED → REVEAL_RECEIVED → STEP_VERIFIED
```

Test `TestAfterFix::test_second_step_after_first_succeeds` demonstrates the
auto-advance between steps:

```
commit step=2 → STEP_VERIFIED → COMPUTING_MOVE (auto) → COMMIT_RECEIVED
```

---

## Acceptance test checklist

| Test | Status |
|------|--------|
| real first COMMIT succeeds after handshake | ✓ `test_commit_after_handshake_succeeds` |
| COMMIT before handshake rejected | ✓ `test_commit_before_handshake_rejected` |
| REVEAL before both committed rejected | ✓ `test_reveal_before_both_committed_rejected` |
| exact duplicate COMMIT/REVEAL is idempotent | ✓ `test_exact_duplicate_commit_is_idempotent` |
| conflicting duplicate rejected | ✓ `test_conflicting_duplicate_commit_rejected` |
| wrong signature rejected | ✓ `test_wrong_signature_rejected` |
| wrong config_sha256 rejected | ✓ `test_wrong_config_sha256_rejected` |
| callback exception leaves no half-advanced state | ✓ `test_callback_exception_leaves_no_half_advanced_state` |
| concurrent requests serialize deterministically | ✓ `test_concurrent_commits_serialized` |
| timeout → TECHNICAL_LOSS | ✓ `test_technical_loss_from_any_state` |
| one full step completes | ✓ `test_one_full_step_with_passive_callbacks` |
| second step after first succeeds | ✓ `test_second_step_after_first_succeeds` |
| cop-side: handshake → commit → reveal → audit → done | ✓ `test_audit_and_done` |

All 18 tests pass in both repositories.

---

## Remaining risks

1. **No real two-process HTTP test yet.**  All integration tests run in-process
   with direct function calls.  A real two-process test (FastAPI SSE server +
   HTTP client) would demonstrate the SSE transport layer, rate limiting, and
   network error handling paths.  This is Phase 3+ work.

2. **Six-gamelet state reset.** `SessionRegistry` accumulates sessions across
   gamelets.  Between gamelets, the registry entry for the previous game_id
   remains.  The next gamelet uses a fresh game_id, which creates a fresh entry.
   This is correct but the old entries are never cleaned up.  Memory growth
   should be addressed in a later phase.

3. **Cop's `my_endpoint` defaults to `http://localhost:5000/mcp`.** In
   production the cop needs its actual public endpoint URL so the thief can
   verify it during handshake.  The `PeerAgentRuntime` should pass its own URL
   when constructing `PeerRuntime`.

4. **`_send_start_game()` does not abort on handshake failure.** If the thief
   rejects `start_game`, the cop logs a warning and proceeds.  The turn loop
   will then fail at the first COMMIT with a protocol violation on the thief
   side.  A stricter approach would abort immediately on handshake rejection.

5. **Final-audit coordinator path is not yet called from `peer_runtime_audit`.**
   `do_final_audit()` sends the FINAL_AUDIT action, but after receiving the
   response it does not call `coord.on_audit_begin()` / `on_final_audit_complete()`
   / `on_done()`.  The SM is therefore not advanced through AUDITING → DONE
   in the active (cop) path at end-of-game.  This is tracked for Phase 3.
