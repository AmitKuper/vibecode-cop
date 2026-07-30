# vibecode-cop — Cop Agent

Autonomous AI cop agent for the Cop & Thief P2P game. Runs as an MCP server on port 5000 and
an MCP client that connects to the thief agent.

## Quick Start

```bash
uv sync
cp config.toml.example config.toml   # edit peer_url to thief's URL
python -m cop
```

## Architecture

- MCP server (port 5000) receives thief's commits and reveals
- MCP client connects to thief's port to send commits and reveals
- Commit-reveal protocol: SHA-256(canonical_json({game_id, gamelet, step, role, state_hash, move, hint, intent, nonce}))
- RL strategy (DQN/Q-table/Greedy) → fast path <1ms; LLM crew fallback for cold start
- Scent field observation: cop sees Chebyshev distance decay, never true thief position

### Component Overview

```
cop/__main__.py
  └── PeerRuntime (agent/peer_runtime.py)
        ├── MCP Server :5000    ← receives thief's action/commit/reveal/start_game
        ├── MCP Client          ← sends cop's action/commit/reveal to thief
        ├── PeerTurnLoop        ← commit → send → receive → verify → apply
        ├── RulesEngine         ← local game state, no shared memory
        ├── RLPolicy            ← DQN/Q-table/Greedy strategy selection
        ├── CrewAI Agents       ← LLM fallback for cold start
        └── ReportManager       ← file + Gmail reporting after each gamelet
```

## Configuration

Copy `config.toml.example` to `config.toml` and set:

- `[cop] peer_url` — thief agent's MCP URL (e.g. `http://opponent.ngrok.io/mcp`)
- `[crypto] shared_secret` — pre-agreed secret with opponent
- `[llm] model` — Claude model for LLM strategy (default: claude-haiku-4-5-20251001)

## Protocol

Each turn follows a two-round commit-reveal exchange:

```
Cop Agent                           Thief Agent
    │── COMMIT(h_commit_cop) ──────────► │
    │◄─ ACK(h_commit_thief) ────────────│
    │── REVEAL(move, hint, nonce) ─────► │
    │◄─ ACK(opp_move, opp_nonce) ───────│
    │  verify(h_commit_thief, opp_reveal)│
    │  apply_moves(); check_status()     │
```

Commitment: `h_commit = SHA-256(canonical_json({game_id, gamelet, step, role, state_hash, move, hint, intent, nonce}))`

A mismatch at verification triggers `TECHNICAL_LOSS` for the offending agent.

## Hidden Information

The cop's observation contains a scent field (Chebyshev distance decay) — never the thief's true position:

```
scent[x][y] = 0.9 × 0.10^(chebyshev_distance(cop_pos, thief_pos))
```

This satisfies the role-filtered hidden-info requirement (AC4).

## Running a Full Series

```bash
python scripts/run_series.py --cop-url http://localhost:5000 --thief-url http://localhost:5001
```

Or start the cop directly and let the thief connect:

```bash
python -m cop
```

## Auditing a Game Log

```bash
python scripts/replay_viewer.py cop/games/log_*.json
```

Verifies SHA-256 integrity of every step in the log and re-checks all commitment hashes offline.

## Tests

```bash
uv run pytest
```

121 tests, all passing (2 skipped for live network only). Coverage includes:

- `test_shared_config_contract.py` (19 tests) — SHA-256 config lock
- `test_peer_runtime_no_central_judge.py` (32 tests) — P2P invariants
- `test_replay_audit.py` (8 tests) — tamper detection
- `test_thief_rl_no_true_cop_position.py` (8 tests) — hidden info
- `test_game_series_six_gamelets.py` (7 tests) — series scoring
- `test_network_timeout_technical_loss.py` (3 tests) — watchdog
- and more (see `tests/`)

## Shared Config

`config/game.json` is the single source of truth for all agreed game parameters. Both agents
compute and embed its SHA-256 in every MCP message. Fixed values (diagonal_moves, pheromone
parameters, technical_loss) are validated at startup; mismatches abort the match.

## Scoring

| Outcome | Cop pts | Thief pts |
|---------|---------|-----------|
| Cop captures thief | 20 | 5 |
| Thief survives max turns | 5 | 10 |
| Tie | 2 | 2 |
| TECHNICAL_LOSS | 0 | 0 |

Values are loaded from `config/game.json` at runtime.

## Technology Stack

| Component | Library |
|-----------|---------|
| MCP transport | `fastmcp` ≥0.9 |
| LLM strategy | `crewai` ≥0.86 + `anthropic` ≥0.43 |
| RL training | `torch` ≥2.3 |
| Gmail reporting | `google-api-python-client` ≥2.0 |
| Package mgmt | `uv` ≥0.4 |
