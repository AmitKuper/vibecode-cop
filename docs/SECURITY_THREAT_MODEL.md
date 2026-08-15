# Security Threat Model — Cop-Thief P2P Protocol

## Threat Surface

The cop-thief game runs as two independent OS processes communicating over HTTP/MCP.
No trusted third party exists after protocol negotiation. Each side must defend itself.

---

## Threats and Mitigations

### T1 — Replay Attack
**Threat:** Adversary re-sends a previously valid COMMIT or REVEAL for an earlier step.

**Mitigation:**
- `ProtocolCoordinator` enforces monotonically increasing step numbers.
- Any `step <= last_accepted_commit_step` is rejected with an out-of-order error.
- Idempotency records are keyed on `(game_id, gamelet, role, step, phase)`.

---

### T2 — Commitment Tampering
**Threat:** Player claims a different move during REVEAL than was committed.

**Mitigation:**
- `h_commit = SHA-256(game_id || step || role || state_hash || move || nonce)`.
- Reveal payload is verified against the stored commitment hash.
- Mismatch triggers `TECHNICAL_LOSS` via `do_final_audit`.

---

### T3 — One-Sided Audit (Selective Disclosure)
**Threat:** Player refuses to disclose nonces or reveals only winning steps.

**Mitigation:**
- Final audit requires disclosure of ALL step nonces.
- `local_nonces` are persisted in `RecoveryState` to survive crashes.
- Failure to produce matching nonces results in `commitment_mismatch` loss.

---

### T4 — Fake Result Injection
**Threat:** Player sends a fabricated `game_end` message claiming a win.

**Mitigation:**
- Each side computes winner independently from `RulesEngine`.
- `notify_game_end` is informational only; local game state governs the result.
- Results written to disk (`write_result`) use locally computed values.

---

### T5 — Process Freeze / Hang
**Threat:** Main process hangs on a network call or deadlock; opponent gains time advantage.

**Mitigation:**
- Per-call deadlines on every outbound MCP call and bounded polls on every inbound
  wait (`cop_worker/net_gateway.py`; `[timeouts]` in `config/runtime.toml`).
- **Independent OS-process Watchdog** (`cop_worker/reliability/watchdog.py`, launched
  by `scripts/ref3_match/watchdog_bridge.py`) monitors heartbeats from outside the
  event loop — immune to asyncio event loop stalls. `WorkerProc` covers a wedged role
  process; the watchdog covers the coordinating process itself.
- Threshold: `HEARTBEAT_INTERVAL_S * THRESHOLD_MULTIPLIER = 15 s` before SIGTERM.
- Failure evidence written to disk before kill for post-mortem analysis.

---

### T6 — Crash without Recovery
**Threat:** Process crash loses in-flight commitment data; audit fails.

**Mitigation:**
- `RecoveryState` persists `local_nonces`, `local_commitments`, SM state, and step counters.
- Atomic writes (`tmp + os.replace`) prevent partial state files.
- `DeadlineTracker` persists retry metadata for bounded retries with exponential back-off.

---

### T7 — Deadline Exhaustion / Retry Storm
**Threat:** Unbounded retries exhaust resources or enable time-of-check attacks.

**Mitigation:**
- `DeadlineTracker` enforces `max_attempts` and absolute expiry per request.
- Exponential back-off with ±20% jitter prevents synchronised retry storms.
- Terminal status (`TIMEOUT`, `PERMANENT_FAIL`) prevents further retries.

---

## EXTERNAL_PENDING — Not Yet Mitigated

| Item | Risk | Required Mitigation |
|------|------|---------------------|
| Public tunnel (ngrok/localtunnel) | MITM, eavesdropping | TLS with certificate pinning |
| Opponent identity | Impersonation | Ed25519 mutual authentication on start_game |
| Secret token leakage | Full protocol break | Rotate `secret` per session; store in vault |
| Watchdog evidence tampering | Evidence falsified | Sign evidence file with session key |

---

*Schema version: Phase 7 — generated 2026-08-03*
