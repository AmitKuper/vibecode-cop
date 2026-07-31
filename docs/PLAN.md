# Implementation Plan — Cop Agent (vibecode-cop)
**Version:** 1.2 | **Group:** vibecode | **Date:** 2026-07-30

---

## 1. C4 Model — Cop Agent

### Level 1 — System Context

```
┌─────────────────────────────────────────────────────────────────────┐
│                         External Actors                             │
│                                                                     │
│  [League Admin]    [Human Auditor]    [Gmail API]    [Claude API]   │
│       │                  │                │               │         │
└───────┼──────────────────┼────────────────┼───────────────┼─────────┘
        │                  │                │               │
        ▼                  ▼                ▼               ▼
┌───────────────────────────────────────────────────────────────────┐
│                       vibecode-cop                                │
│                                                                   │
│  Autonomous cop agent that pursues the thief across a 7×7 grid   │
│  using MCP-based commit-reveal protocol and RL strategy.         │
│  No shared memory with thief; no central referee.                │
└───────────────────────────────────────────────────────────────────┘
```

### Level 2 — Container Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                          vibecode-cop Process                        │
│                                                                      │
│  ┌─────────────────┐        MCP/HTTP         ┌──────────────────┐   │
│  │  MCP Server     │ ◄──────────────────────► │  Thief Agent     │   │
│  │  Port :5000     │    commit/reveal msgs    │  Port :5001      │   │
│  │  (FastMCP)      │                          └──────────────────┘   │
│  └─────────────────┘                                                 │
│  ┌─────────────────┐                                                 │
│  │  MCP Client     │ ─────────────────────────► (thief:5001)        │
│  │  (FastMCP)      │                                                 │
│  └─────────────────┘                                                 │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    PeerRuntime                              │    │
│  │   game_id, role="cop", board, config_sha256, game_dir       │    │
│  └─────────────────────────────────────────────────────────────┘    │
│           │                                                          │
│    ┌──────┼──────────────────────────────────────────────┐          │
│    ▼      ▼             ▼              ▼                 ▼          │
│  PeerTurnLoop  RulesEngine    RLPolicy          ReportManager       │
│  PeerAudit     Board          GreedyStrategy    FileJSON            │
│                               LLM CrewAI        GmailPlugin         │
└──────────────────────────────────────────────────────────────────────┘
```

### Level 3 — Component Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                       cop/__main__.py                                │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  PeerRuntime (agent/peer_runtime.py)                        │    │
│  │                                                             │    │
│  │  ┌──────────────────┐  ┌─────────────────────────────────┐ │    │
│  │  │ PeerTurnLoop     │  │  MCP Protocol Layer             │ │    │
│  │  │ 1. build_state   │  │  agent/mcp/server.py (FastMCP)  │ │    │
│  │  │ 2. hash_state    │  │  agent/mcp/client.py (FastMCP)  │ │    │
│  │  │ 3. select_move   │  │  agent/mcp/crypto.py            │ │    │
│  │  │ 4. commit        │  │  agent/mcp/messages.py          │ │    │
│  │  │ 5. send_commit   │  └─────────────────────────────────┘ │    │
│  │  │ 6. send_reveal   │                                       │    │
│  │  │ 7. verify_opp    │  ┌─────────────────────────────────┐ │    │
│  │  │ 8. apply_moves   │  │  Strategy Layer                 │ │    │
│  │  │ 9. check_status  │  │  agent/rl/policy.py (DQN/Qtbl)  │ │    │
│  │  └──────────────────┘  │  agent/rl/strategies.py         │ │    │
│  │                        │  agent/orchestrator_crew.py     │ │    │
│  │  ┌──────────────────┐  └─────────────────────────────────┘ │    │
│  │  │ RulesEngine      │                                       │    │
│  │  │ agent/rules_engine.py                                    │    │
│  │  │ agent/board.py                                           │    │
│  │  └──────────────────┘                                       │    │
│  └─────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 2. MCP Turn Sequence (Cop's Perspective)

```
cop/__main__.py         PeerTurnLoop         Thief MCP Server
      │                      │                      │
      │── run_peer_turn() ──►│                      │
      │                      │── 1. build_state     │
      │                      │── 2. hash_state      │
      │                      │── 3. select_move ──► RLPolicy/Greedy/LLM
      │                      │── 4. create_commit   │
      │                      │── COMMIT(h_commit) ──────────────►│
      │                      │◄─ ACK(opp_h_commit) ─────────────│
      │                      │── REVEAL(move, nonce) ────────────►│
      │                      │◄─ ACK(opp_move, opp_nonce) ───────│
      │                      │── 7. verify_opp_reveal            │
      │                      │       mismatch? → TECHNICAL_LOSS  │
      │                      │── 8. apply_moves(cop, thief)      │
      │                      │── 9. check_game_status            │
      │◄─ (outcome) ─────────│                      │
```

### Game Startup (Step-0 Declaration)

```
League Admin          cop/__main__          Thief MCP Server
     │                    │                      │
     │── python -m cop ──►│                      │
     │                    │── start_game() ──────►│
     │                    │◄─ ACK ───────────────│
     │                    │                      │
     │                    │  write declaration_*.json
     │                    │  (hardware, LLM, git SHA, config SHA-256)
     │                    │                      │
     │                    │── run gamelet g01 ───►│
     │                    │   ...                │
     │                    │── run gamelet g06 ───►│
     │                    │── PeerAudit.audit()  │
     │                    │── ReportManager.run()│
```

---

## 3. Strategy Selection Flowchart

```
select_move() called
        │
        ▼
  models/cop_dqn.pt exists?
    ├─ Yes ──► DQN inference ──► move  (< 1ms)
    └─ No
        ▼
  models/cop_qtable.npy exists?
    ├─ Yes ──► Q-table lookup ──► move  (< 0.1ms)
    └─ No
        ▼
  GreedyCopStrategy (always available)
    ──► minimize Chebyshev(cop_pos, scent_peak) ──► move
        │
        └─ OR if config.llm_fallback=true:
            CrewAI GameManager + StrategyAgent ──► move  (1-5 sec)
```

---

## 4. Design Decisions

### AD-1: No Central Judge (P2P Architecture)
**Rationale:** The spec explicitly forbids a central game server. Each agent independently verifies game state.

**Trade-offs:**
- Pro: No single point of failure; fully decentralized
- Con: 2 RTTs per turn (commit + reveal) instead of 1
- Con: Both agents must apply moves identically; disagreement → TECHNICAL_LOSS

**Implementation:** `PeerRuntime` + `peer_turn_loop.py`

### AD-2: SHA-256 Commitment Scheme
**Rationale:** Prevents move-order advantage. Neither agent can choose their move after seeing the opponent's.

**Commitment payload:**
```json
{
  "game_id": "...",
  "gamelet": "g01",
  "step": 1,
  "role": "cop",
  "state_hash": "SHA-256(board_state)",
  "move": "N",
  "hint": "pursuing",
  "intent": "close distance",
  "nonce": "random-uuid"
}
```

The `gamelet` field prevents replaying a valid commitment from a different gamelet.

### AD-3: Scent Field for Cop Observation
**Rationale:** Pure distance information would trivially solve the game. Scent field gives directional signal without exact position.

**Formula:** `scent[x][y] = 0.9 × 0.10^(chebyshev(cop, thief_last))`

**Trade-off:** Cop can infer approximate thief location from scent peak, but cannot know exact position after thief moves.

### AD-4: Multi-Level Strategy Fallback
**Rationale:** RL models may not be present on first run. Greedy strategy ensures the cop can always make a legal move. LLM crew provides creative play for cold start.

**Order:** DQN → Q-table → Greedy → LLM

### AD-5: HMAC-SHA256 Message Authentication
**Rationale:** Prevents man-in-the-middle attacks between cop and thief processes.

**Implementation:** `agent/mcp/crypto.py` — every MCP message carries `hmac_sha256(shared_secret, canonical_json(payload))`.

---

## 5. Technology Stack

| Component | Library | Version | Purpose |
|-----------|---------|---------|---------|
| MCP transport | `fastmcp` | ≥0.9 | Server and client MCP endpoints |
| LLM strategy | `crewai` | ≥0.86 | GameManager + StrategyAgent crew |
| Claude API | `anthropic` | ≥0.43 | LLM backend for strategy crew |
| RL training | `torch` | ≥2.3 | DQN/PPO policy networks |
| RL env | custom `gymnasium`-style | — | 7×7 grid environment |
| Gmail reporting | `google-api-python-client` | ≥2.0 | OAuth 2.0 gmail.send |
| Package mgmt | `uv` | ≥0.4 | Fast dependency resolution |
| Testing | `pytest` | ≥8.0 | 121 tests |
| Linting | `ruff` | ≥0.4 | Zero violations enforced |

---

## 6. File Structure

```
cop/
├── __init__.py          ← package init; exports CopAgent
└── __main__.py          ← entry point; builds PeerRuntime and calls run()

agent/
├── board.py             ← 7×7 grid, legal moves, barrier checking
├── rules_engine.py      ← apply_moves, check_game_status, GameOutcome
├── peer_runtime.py      ← top-level coordinator; owns game_id and role
├── peer_turn_loop.py    ← full turn: commit → reveal → verify → apply
├── peer_audit.py        ← post-game SHA-256 log audit
├── game_runner.py       ← dev self-play runner (not used in production P2P)
├── game_series.py       ← 6-gamelet series coordinator
├── orchestrator.py      ← base orchestrator
├── orchestrator_crew.py ← CrewAI crew definition
├── orchestrator_phase.py ← phase management
├── orchestrator_game.py ← game-level orchestration
├── config/
│   ├── __init__.py
│   └── shared_config.py ← load, validate, SHA-256 of config/game.json
├── mcp/
│   ├── server.py        ← FastMCP server; handles action/commit/reveal/start_game
│   ├── client.py        ← FastMCP client; sends to peer
│   ├── crypto.py        ← SHA-256 commit, HMAC auth, nonce generation
│   ├── messages.py      ← message schemas
│   ├── messages_game.py ← game-specific message types
│   ├── protocol.py      ← protocol state machine
│   ├── log.py           ← structured game log writer
│   └── log_replay.py    ← offline log audit
├── rl/
│   ├── policy.py        ← RLPolicy: DQN/Q-table inference
│   ├── strategies.py    ← GreedyCopStrategy, ComboCopStrategy
│   ├── environment.py   ← RL gymnasium-style env
│   ├── train.py         ← training entry point
│   └── ...
└── reports/
    ├── manager.py       ← ReportManager: orchestrates plugins
    ├── gmail_report.py  ← Gmail OAuth 2.0 send
    ├── gatekeeper.py    ← quota + idempotency guard
    └── ...
```
