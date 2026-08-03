# Phase 2 State Machine Report — vibecode-cop

**Date:** 2026-08-03  
**Starting SHA:** `e411836` (Phase 1 commit)

## Summary

Phase 2 made the protocol state machine the mandatory authority for all inbound
and outbound MCP operations.  The machine expanded from 6 states to 16, and
every production handler now acquires a per-session lock before checking or
mutating state.

---

## 2.1 16-State Protocol Machine

**Modified file:** `agent/mcp/protocol.py`

The old `ProtocolStateMachine` had 6 states (IDLE, HANDSHAKE, PLAYING,
AUDITING, DONE, ABORTED) driven by `ProtocolPhase` transitions.  The new
machine has 16 states driven directly by `ProtocolState` transitions.

### States

| State | Role |
|-------|------|
| IDLE | No active session |
| STEP0_NEGOTIATING | start_game received, config being verified |
| READY | Handshake complete |
| COMPUTING_MOVE | Local agent selecting move |
| COMMIT_SENT | We sent our H(move\|nonce) to peer |
| COMMIT_RECEIVED | Peer's commit arrived first |
| BOTH_COMMITTED | Both sides committed |
| REVEAL_SENT | We sent our reveal |
| REVEAL_RECEIVED | Peer's reveal arrived first |
| STEP_VERIFIED | Both reveals accepted; step complete |
| AUDITING | Final nonce audit |
| RESULT_AGREEMENT | Bilateral agreement recorded |
| REPORTING | Sending reports |
| DONE | Terminal — session complete |
| TECHNICAL_LOSS | Terminal — timeout / violation |
| ABORTED | Terminal — abort received |

Terminal states (DONE, TECHNICAL_LOSS, ABORTED) reject all further transitions.
ABORTED and TECHNICAL_LOSS are reachable from any non-terminal state.

Backwards-compatibility shim: `ProtocolPhase` and `StepPhaseTracker` remain
importable to avoid breaking existing callers.

---

## 2.2 Session Registry

**New file:** `agent/mcp/session_registry.py`

`SessionRegistry` maps `(game_id, gamelet_num, local_role) → SessionEntry`.

Each `SessionEntry` holds:
- `sm: ProtocolStateMachine` — the session's state machine
- `lock: threading.Lock` — per-session mutex
- `commit_sent_step / reveal_sent_step` — step tracking for outbound events

The registry is a module-level singleton accessed via `get_registry()`.

---

## 2.3 Handler Integration

**Modified file:** `agent/mcp/server_handlers.py`

Both `handle_start_game()` and `handle_action()` now:
1. Acquire `entry.lock` before any check or mutation
2. Call `entry.sm.can_transition()` / guard helpers
3. Return `{"ok": False, "error": "Protocol violation: ..."}` on illegal ordering
4. Mutate state only after all checks pass

Outbound notification functions added:
- `notify_commit_sent()` / `notify_reveal_sent()` — called by orchestrator
- `notify_step_begin()` — called at start of each step
- `notify_audit_begin()` / `notify_done()` / `notify_technical_loss()`

Gamelet number extracted from game_id suffix (`<uuid>_g<N>`) for per-gamelet
state isolation; bare game_ids default to gamelet 0.

---

## 2.4 Adversarial Tests

**New file:** `tests/test_protocol_state_machine.py` — 31 tests

| Class | Coverage |
|-------|----------|
| TestHappyPath | Full lifecycle (cop-first, thief-first, multi-step, audit) |
| TestIllegalOrderings | 7 invalid sequences rejected |
| TestDuplicateMessages | Duplicate commit/reveal/start_game rejected |
| TestTerminalStates | DONE/ABORTED/TECHNICAL_LOSS reject all; both reachable from any non-terminal |
| TestConcurrencySafety | Registry idempotent under 20 threads; concurrent commits serialized (1 wins, 4 fail) |
| TestGuardHelpers | All guard methods with OK and fail cases |
| TestSerialization | Round-trip to_dict/from_dict for all 16 states |

---

## Quality Gate Results

| Gate | Result |
|------|--------|
| pytest | 692 passed, 0 failed |
| ruff check | All checks passed |
| ruff format | 4 files reformatted |
