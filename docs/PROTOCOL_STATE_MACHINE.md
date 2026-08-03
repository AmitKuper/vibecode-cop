# Protocol State Machine — vibecode-cop / vibecode-thief

**Phase:** 2  
**Date:** 2026-08-03

## Overview

Each gamelet session advances through 16 states.  Terminal states (DONE,
TECHNICAL_LOSS, ABORTED) reject all further transitions.

## State Diagram (ASCII)

```
                        ┌────────────────────────────────────────────────┐
                        │  Any non-terminal state                        │
                        │  ──────────────────────────────────────────→   │
                        │                                ABORTED         │
                        │  ──────────────────────────────────────────→   │
                        │                                TECHNICAL_LOSS  │
                        └────────────────────────────────────────────────┘

  IDLE
    │  start_game received
    ▼
  STEP0_NEGOTIATING
    │  config confirmed
    ▼
  READY ◄─────────────────────────────────────────────────────────────────┐
    │  step begins                                                         │
    ▼                                                                      │
  COMPUTING_MOVE                                                           │
    │                    │                                                 │
    │ cop sends commit   │ peer commit arrives first                       │
    ▼                    ▼                                                 │
  COMMIT_SENT       COMMIT_RECEIVED                                        │
    │ peer commit        │ cop sends commit                                │
    │ arrives            │                                                 │
    └──────────┬─────────┘                                                 │
               ▼                                                           │
          BOTH_COMMITTED                                                   │
               │                    │                                      │
               │ cop sends reveal   │ peer reveal arrives first            │
               ▼                    ▼                                      │
          REVEAL_SENT          REVEAL_RECEIVED                             │
               │ peer reveal        │ cop sends reveal                     │
               │ arrives            │                                      │
               └──────────┬─────────┘                                      │
                          ▼                                                │
                    STEP_VERIFIED ─────── (next step) ────────────────────┘
                          │  (final step)
                          ▼
                       AUDITING
                          │  mutual audit complete
                          ▼
                    RESULT_AGREEMENT
                          │  both sides agree
                          ▼
                       REPORTING
                          │  reports sent
                          ▼
                        DONE   (terminal)
```

## State Descriptions

| State | Description |
|-------|-------------|
| IDLE | No session active |
| STEP0_NEGOTIATING | `start_game` received, config being validated |
| READY | Handshake complete, ready to receive steps |
| COMPUTING_MOVE | Local agent computing its move for this step |
| COMMIT_SENT | We sent our H(move\|nonce) to the peer; awaiting their commit |
| COMMIT_RECEIVED | Peer's commit arrived before ours was sent |
| BOTH_COMMITTED | Both sides have committed; ready for reveal phase |
| REVEAL_SENT | We sent our reveal; awaiting peer reveal |
| REVEAL_RECEIVED | Peer's reveal arrived before ours was sent |
| STEP_VERIFIED | Both reveals received and verified; step complete |
| AUDITING | Final nonce audit in progress |
| RESULT_AGREEMENT | Bilateral result agreed |
| REPORTING | Sending reports to league ledger / Gmail |
| DONE | Session complete (terminal) |
| TECHNICAL_LOSS | Timeout, protocol violation, or unrecoverable error (terminal) |
| ABORTED | Peer sent ABORT or local abort declared (terminal) |

## Concurrency Model

Each `(game_id, gamelet_num, local_role)` tuple maps to a `SessionEntry`
containing:
- A `ProtocolStateMachine` instance
- A `threading.Lock`

All inbound MCP handlers acquire `entry.lock` before checking or mutating
state.  The check and mutate are atomic within the lock scope, preventing
TOCTOU races where two concurrent peer commits could both succeed.

## Outbound notification hooks

| Function | When to call |
|----------|--------------|
| `notify_step_begin()` | Before orchestrator computes move |
| `notify_commit_sent()` | After successfully sending commit to peer |
| `notify_reveal_sent()` | After successfully sending reveal to peer |
| `notify_audit_begin()` | Before requesting nonces from peer |
| `notify_done()` | After result agreement and reports sent |
| `notify_technical_loss()` | On timeout or unrecoverable error |
