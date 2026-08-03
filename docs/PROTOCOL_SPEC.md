# P2P Cop-and-Thief Protocol Specification

## Overview

Two peers (cop, thief) play a series of gamelets over a direct HTTP/SSE connection.
No central judge exists. All integrity guarantees are cryptographic and bilateral.

---

## 1. 16-State State Machine

| # | State | Description |
|---|-------|-------------|
| 0 | IDLE | Session not yet started |
| 1 | STEP0_NEGOTIATING | Exchanging Step-0 declarations |
| 2 | READY | Handshake complete; ready to play |
| 3 | COMPUTING_MOVE | Agent is computing its next move |
| 4 | COMMIT_SENT | Local commitment sent; awaiting peer |
| 5 | COMMIT_RECEIVED | Peer commitment received; sending ours |
| 6 | BOTH_COMMITTED | Both commitments on record |
| 7 | REVEAL_SENT | Local reveal sent; awaiting peer |
| 8 | REVEAL_RECEIVED | Peer reveal received; sending ours |
| 9 | STEP_VERIFIED | Both reveals verified; step complete |
| 10 | AUDITING | Final audit in progress |
| 11 | RESULT_AGREEMENT | Audit passed; exchanging signed results |
| 12 | REPORTING | Writing ledger / email report |
| 13 | DONE | Session complete |
| 14 | TECHNICAL_LOSS | Protocol violation detected |
| 15 | ABORTED | Session aborted by mutual consent |

---

## 2. Commit-Reveal Protocol (per turn)

### 2a. Commitment

Each peer independently computes:

```
nonce       = secrets.token_hex(32)
h_commit    = SHA-256(canonical_json({game_id, gamelet, step, role,
                                       state_hash, move, hint, intent, nonce}))
```

Peers exchange `h_commit` values. Neither peer can alter their move after committing.

### 2b. Nonce Exchange (reveal)

After both commitments are received, each peer sends their plaintext move + nonce.
The receiver recomputes `h_commit` and verifies it matches the earlier commitment.
A mismatch triggers `TECHNICAL_LOSS`.

---

## 3. Step-0 (Bilateral Declaration)

Before any gameplay, each peer constructs a `PeerDeclaration` containing:
- Team identity, git SHA, model SHA-256
- Config SHA-256, scent model hash
- Ed25519 public key

Declarations are signed with ephemeral Ed25519 keys (`generate_key_pair()`).
Private keys are never written to disk.

A `DeclarationAgreement` records both peers' declaration hashes for the ledger.

---

## 4. Per-Step Evidence Journal

Each step appends a `StepEvidence` record to a `StepJournal`.
The journal maintains a hash chain:

```
genesis_hash = SHA-256(b"genesis")
chain[i]     = SHA-256(chain[i-1] || canonical_json(entry[i]))
```

The chain root is the `transcript_root` for the gamelet.
`verify_chain()` recomputes all hashes and detects any tampering.
Writes are atomic via `tmp + os.replace()`.

---

## 5. Bilateral Audit

At game end, the active peer (cop) sends `FINAL_AUDIT` with its nonces.
The passive peer responds with its nonces.
Each peer independently verifies all opponent commitments.

An `AuditSummary` is produced per gamelet:
- `audit_status`: `PASSED` | `FAILED` | `NOT_APPLICABLE` (zero-turn abort)
- `transcript_root`: final chain hash
- Signed with the peer's ephemeral Ed25519 key

---

## 6. Result Consensus

After audit, both peers produce a `ResultAgreement` and call
`verify_bilateral_consensus(local, remote)`.

The function computes `consensus_fields_hash()` for both sides —
covering `gamelet_outcomes`, `cop_total_score`, `thief_total_score`,
`series_winner`, and `counted_status` — and raises `ResultConsensusError`
if they differ.

Only when consensus is confirmed does the ledger get updated.

---

## 7. Security Properties

| Property | Mechanism |
|----------|-----------|
| Move integrity | Commit-reveal with SHA-256 |
| Identity binding | Ed25519 signatures on declarations |
| Audit tamper-evidence | SHA-256 hash chain in StepJournal |
| Bilateral agreement | consensus_fields_hash comparison |
| Replay prevention | Monotonically increasing step counters |
| Idempotency | (game_id, gamelet, role, step, phase) cache |
