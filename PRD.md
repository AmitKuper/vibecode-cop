# Product Requirements Document — Cop Agent (vibecode-cop)
**Version:** 1.2 | **Group:** vibecode | **Date:** 2026-07-30

---

## 1. Role Overview

The **Cop Agent** is one half of a fully decentralized P2P multi-agent game. Its objective is to **capture the thief** — to occupy the same cell as the thief within 35 moves per gamelet. Over a series of six gamelets the cop accumulates score: 20 points per capture, 5 points if the thief survives (partial credit for forcing close finishes).

The cop agent runs as an autonomous AI process that:
- Binds an MCP server on port 5000
- Connects as an MCP client to the thief's port
- Independently verifies every move commitment from the thief
- Applies game rules locally without a central referee
- Observes the board through a **scent field** (Chebyshev distance decay from thief's last known position) — never the thief's true position

### Strategic Objective
Hunt the thief across a 7×7 grid, using scent field signals, barrier awareness, and learned RL policies to close distance efficiently. The cop must balance aggressive pursuit against the risk of being drawn into corners where the thief can evade.

---

## 2. Acceptance Criteria

| # | Criterion | Verification |
|---|-----------|--------------|
| AC1 | Cop runs as a separate OS process with no shared memory with thief | `ps aux` shows two PIDs; no shared Python state |
| AC2 | Cop is simultaneously an MCP server (:5000) and MCP client | Cop binds :5000, connects to thief's port; both directions active |
| AC3 | Cop's commitment hash matches SHA-256 of canonical JSON at final audit | `tests/test_replay_audit.py` — tamper detection tests |
| AC4 | Cop observation never contains true thief position | `tests/test_thief_rl_no_true_cop_position.py` (8 tests) |
| AC5 | GUI live view `/api/games/{id}/live/cop` omits `thief_position` | `tests/test_live_gui_role_filtering.py` (5 tests) |
| AC6 | Six gamelets run per series; cop scores aggregate correctly | `tests/test_game_series_six_gamelets.py` (7 tests) |
| AC7 | Watchdog timeout causes TECHNICAL_LOSS | `tests/test_network_timeout_technical_loss.py` (3 tests) |
| AC8 | config/game.json SHA-256 validated at game start | `tests/test_shared_config_contract.py` (19 tests) |
| AC9 | Gmail sends using only `gmail.send` scope | OAuth token inspection; gatekeeper blocks repeated sends |
| AC10 | All 121 tests pass with zero Ruff violations | `uv run pytest` and `uv run ruff check .` |

---

## 3. User Stories (Cop Perspective)

### Cop Agent
- **As the cop agent**, I want to receive a scent field approximating thief proximity so that I can plan moves without seeing the thief's exact position, ensuring fair information asymmetry.
- **As the cop agent**, I want every move I commit to be cryptographically signed so that the thief cannot claim I changed my move after seeing theirs.
- **As the cop agent**, I want the thief's reveal to be verified against their earlier commitment so that I can detect any tampered move and trigger a TECHNICAL_LOSS.
- **As the cop agent**, I want to fall back to an LLM strategy crew when no trained RL model is available so that I can participate in a match even cold.
- **As the cop agent**, I want my game log to be written to disk after every gamelet so that any auditor can verify my move history offline.

### League Administrator
- **As a league administrator**, I want six gamelets per match with aggregate scoring so that individual luck is averaged out over a series.
- **As a league administrator**, I want both agents to compute the same SHA-256 of `config/game.json` so that I can confirm they played under identical parameters.

### Security Auditor
- **As a security reviewer**, I want the shared config to be SHA-256 locked so that the cop cannot unilaterally change agreed-upon parameters mid-match.
- **As a compliance officer**, I want credentials and tokens excluded from git history so that the OAuth secret is never exposed in the repository.

---

## 4. Functional Requirements

### FR-1: Board & Movement
- FR-1.1: The board is a 7×7 grid, origin top-left, 0-indexed. Cop starts at `[0, 0]`.
- FR-1.2: Legal moves are N, S, E, W, STAY. Diagonal moves are forbidden.
- FR-1.3: Moves that would take the cop out-of-bounds are rejected; cop stays in place.
- FR-1.4: Up to 14 barriers may be placed per game. A barrier blocks entry to that cell.
- FR-1.5: Maximum 35 moves per gamelet (`max_moves = 35`).

### FR-2: Win Conditions (from cop's perspective)
- FR-2.1: **Cop wins gamelet** when cop and thief occupy the same cell after a move.
- FR-2.2: **Cop loses gamelet** when the thief survives `max_moves` steps without being captured.
- FR-2.3: **TECHNICAL_LOSS** (cop scores 0) when audit fails or cop's watchdog expires.

### FR-3: Scoring
| Outcome | Cop pts | Thief pts |
|---------|---------|-----------|
| Cop captures thief (`capture_cop`) | 20 | 5 |
| Thief survives max turns (`survival_thief`) | 5 | 10 |
| Tie (score equal) | 2 | 2 |
| TECHNICAL_LOSS or audit failure | 0 | 0 |

Scoring values are loaded from `config/game.json` at runtime.

### FR-4: Commit-Reveal Protocol (cop's responsibilities)
- FR-4.1: Cop must commit before revealing its move each turn.
- FR-4.2: Cop's commitment: `h_commit = SHA-256(canonical_json({game_id, gamelet, step, role, state_hash, move, hint, intent, nonce}))`.
- FR-4.3: The `gamelet` field in the payload prevents cross-gamelet replay attacks.
- FR-4.4: Cop verifies the thief's reveal matches the thief's earlier commitment.
- FR-4.5: Mismatch at verification → cop declares TECHNICAL_LOSS for the thief, logs `abort_reason`.

### FR-5: Hidden Information (cop's observation)
- FR-5.1: The cop's observation contains a scent field (Chebyshev distance decay from thief's last known position) — never the thief's true position.
- FR-5.2: Scent field formula: `scent[x][y] = 0.9 × 0.10^(chebyshev_distance(cop_pos, thief_pos))`
- FR-5.3: The GUI live-view endpoint `/api/games/{id}/live/cop` omits `thief_position` from the response.

### FR-6: Shared Configuration
- FR-6.1: `config/game.json` is the single source of truth for all agreed game parameters.
- FR-6.2: Cop computes and embeds the SHA-256 of `config/game.json` in every MCP message.
- FR-6.3: Fixed values that cannot be changed: `diagonal_moves=false`, `pheromone_center_intensity=0.9`, `pheromone_decay=0.10`, `pheromone_grid_size=5`, `technical_loss=0`.
- FR-6.4: Minimum enforced values: `max_barriers≥14`, `max_moves≥35`, `survival_threshold≥35`, `num_gamelets≥1`.

### FR-7: Six-Gamelet Series
- FR-7.1: A full match runs exactly 6 gamelets (g01–g06) sequentially.
- FR-7.2: Cop scores accumulate per gamelet; series winner has higher total.
- FR-7.3: Series result is written to `result_{series_id}_series.json`.

### FR-8: Reporting
- FR-8.1: After each gamelet, cop writes: `declaration_{game_id}.json`, `config_{game_id}_g{NN}.json`, `log_{game_id}_g{NN}.json`, `result_{game_id}.json`.
- FR-8.2: `declaration_{game_id}.json` includes hardware (OS, CPU, RAM, GPU), LLM model, git commit SHA, gamelet number, config SHA-256.
- FR-8.3: Gmail report uses OAuth 2.0 with `gmail.send` scope only. Modes: `disabled | dry_run | draft | send`.

### FR-9: Replay & Audit
- FR-9.1: `agent/mcp/log_replay.py` verifies SHA-256 integrity of cop's log files.
- FR-9.2: `scripts/replay_viewer.py` provides a CLI to audit individual cop logs or entire directories.

### FR-10: Network Resilience
- FR-10.1: Every MCP call is wrapped in `asyncio.wait_for` with `response_timeout_sec=30`.
- FR-10.2: Each full turn has a watchdog of `watchdog_timeout_sec=60`.
- FR-10.3: Timeout expiry triggers TECHNICAL_LOSS and terminates the game.

---

## 5. Non-Functional Requirements

| Category | Requirement |
|----------|-------------|
| **Latency** | Cold start to first move: < 30 seconds; RL path turn latency: < 5 seconds |
| **Reliability** | Watchdog prevents infinite hangs; retry logic handles transient network failures |
| **Security** | Credentials never committed; HMAC-SHA256 authenticates every MCP message |
| **Maintainability** | Max 150 lines per file; zero Ruff violations; ≥85% test coverage |
| **Auditability** | Any cop log file can be verified offline without replaying the game |
| **Portability** | Runs on Windows, macOS, Linux; Python 3.11+; managed via `uv` |

---

## 6. Strategy Component PRD

### 6.1 Cop RL Strategy

The cop agent uses a multi-level strategy selection pipeline:

```
1. RL path (primary): DQN or Q-table policy, loaded from models/
2. Greedy fallback: GreedyCopStrategy — minimize Chebyshev distance to thief scent peak
3. LLM crew fallback: CrewAI GameManager + StrategyAgent — used when no model file exists
```

**Scent Field Math**

The cop's RL observation includes a 7×7 scent field:
```
scent[x][y] = center_intensity × decay^(chebyshev_dist(cop_pos, thief_last_pos))
```
where `center_intensity=0.9`, `decay=0.10`, `chebyshev_dist(a, b) = max(|ax-bx|, |ay-by|)`.

This gives the cop a noisy but directional signal. At distance 0 (same cell), scent=0.9. At distance 1, scent=0.09. At distance 2, scent=0.009.

**RL Observation Space**

The cop's observation vector includes:
- `cop_pos` — own exact position (normalized to [0,1])
- `scent_field` — 7×7 scent matrix (flattened)
- `barriers` — 7×7 barrier mask
- `turn` — current step / max_moves

The observation never includes raw `thief_pos` coordinates.

**Action Space**

5 discrete actions: `{N=0, S=1, E=2, W=3, STAY=4}`. Illegal moves (out-of-bounds or blocked by barrier) result in STAY.

**Reward Function (training)**
- `+10` on capture
- `-0.1` per step (time penalty to encourage fast captures)
- `+0.5` if Chebyshev distance to thief decreases (shaped reward)
- `-5` on survival (thief escapes)

**Strategy Selection Flowchart**
```
Has models/cop_dqn.pt?
  ├─ Yes → Load DQN, run inference → move
  └─ No
      Has models/cop_qtable.npy?
        ├─ Yes → Load Q-table, lookup → move
        └─ No
            GreedyStrategy available?
              ├─ Yes → minimize distance → move
              └─ No → LLM CrewAI → move
```
