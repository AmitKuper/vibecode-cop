# PRD — Agent Subsystem

> **Document type:** Component Product Requirements Document
> **Scope:** `agent/` shared package — game logic, MCP protocol, crewAI orchestration, RL strategy
> **Status:** v1.0

---

## 1. Purpose and Scope

The `agent/` package is the shared implementation library used by both the cop process (`cop/`) and the thief process (`thief/`). It provides all game-level logic, inter-agent communication protocol, AI orchestration, and reporting that both roles need without duplication.

Neither `cop/` nor `thief/` contains game-rule logic, board state, or cryptographic protocol code — all of this lives exclusively in `agent/`.

---

## 2. Goals

1. Provide a single authoritative Board and RulesEngine shared by both roles.
2. Implement the MCP commit-reveal protocol with HMAC signing and SHA-256 commitments.
3. Expose crewAI-based orchestration (`GameOrchestrator`) that coordinates agents, tools, and MCP message flow.
4. Provide pluggable RL strategy inference (`RLPolicy`) as a drop-in replacement for heuristic play.
5. Deliver game reports (file + Gmail) at game end without coupling to any specific agent role.
6. Remain importable by both `cop/__main__.py` and `thief/__main__.py` without modification.

---

## 3. Non-Goals

- The `agent/` package does not run games. `GameRunner` exists for integration testing only; live games are driven by two separate OS processes communicating over MCP.
- The `agent/` package does not define which role wins a negotiation or who initiates `start_game` — that is the pre-game negotiation layer.
- The `agent/` package does not contain any web server, HTTP routing, or GUI code. That belongs to `webserver/`.
- The `agent/` package does not hard-code group-specific configuration such as port numbers, opponent URLs, or email recipients.

---

## 4. Key Components

### 4.1 Board (`agent/board.py`)

Immutable-ish dataclass holding game state:

| Field | Type | Description |
|---|---|---|
| `cop_position` | `[x, y]` | Current cop cell |
| `thief_position` | `[x, y]` | Current thief cell |
| `turn` | `int` | Turn counter (0-based) |
| `barriers` | `list[list[int]]` | Blocked cells |
| `grid_size` | `int` | Board dimension (default 7) |

Key methods: `is_valid_position`, `get_candidate_actions`, `place_barrier`.

### 4.2 RulesEngine (`agent/rules_engine.py`)

Stateful rules processor that owns:

- Move validation (`validate_move`)
- Simultaneous move application (`apply_moves`)
- Game-outcome detection (`check_game_status` → `GameOutcome`)
- Scent-field computation (`compute_scent_field`) using Chebyshev decay centred on the thief

`GameOutcome` values: `ONGOING`, `COP_WIN`, `THIEF_WIN`.

### 4.3 GameRunner (`agent/game_runner.py`)

Drives a complete game between two `GameOrchestrator` instances inside a single process. Used by integration tests and the `demo_game.py` script. Not used in production (production uses two separate OS processes).

Responsibilities:
- Calls commit on both agents
- Calls reveal on both agents
- Applies moves via `RulesEngine`
- Calls `final_audit` and verifies all HMAC commitments
- Returns `GameResult` with winner, turns, and move log

### 4.4 GameOrchestrator (`agent/orchestrator.py`)

The main runtime class instantiated by each agent process. It combines:

- `AgentMCPServer` — listens for MCP calls from the opponent
- `GameMCPClient` — sends MCP calls to the opponent
- crewAI `Crew` per game — `StrategyAgent` + `GameManagerAgent`
- `ProtocolDiscovery` — introspects opponent's tool schema at startup
- Per-game disk state in `agent/memory/<game_id>/`

Key MCP handlers:

| Phase | Handler | Description |
|---|---|---|
| `start_game` | `_on_start_game` | Initialises game memory folder, creates crew |
| `commit` | `_handle_commit` | Selects move, creates SHA-256 commitment, stores nonce |
| `reveal` | `_handle_reveal` | Returns pre-committed move and nonce |
| `final_audit` | `_handle_final_audit` | Returns all nonces for cross-verification |
| `game_end` | `_handle_game_end` | Marks game complete, triggers report generation |

Move selection priority: (1) RL policy if a trained checkpoint exists in `models/`, (2) role-specific heuristic from `cop/strategy/` or `thief/strategy/`.

### 4.5 MCP Server (`agent/mcp/server.py`)

FastMCP-based HTTP server that exposes three tools to the opponent:

- `ping` — liveness check
- `start_game` — game handshake (receives `StartGameMessage`)
- `action` — per-turn protocol (receives `ActionMessage` with phase field)

All inbound messages are HMAC-verified before dispatch. The server calls registered `handler_callbacks` supplied by `GameOrchestrator`.

### 4.6 MCP Client (`agent/mcp/client.py`)

HTTP client that calls the opponent's MCP server. Signs all outbound messages with HMAC-SHA256. Raises `MCPError` on timeout or signature mismatch.

### 4.7 Crypto (`agent/mcp/crypto.py`)

Provides:

- `create_commitment(game_id, step, role, state_hash, move, hint, intent)` → `(h_commit, nonce)` — SHA-256 of `(nonce + canonical_json(payload))`
- `verify_commitment(h_commit, nonce, payload)` → `bool`
- `hash_game_state(state_dict)` → SHA-256 hex string
- HMAC signing/verification for MCP messages

### 4.8 Reports Pipeline (`agent/reports/`)

Plugin-based report generation triggered at `game_end`:

| Module | Role |
|---|---|
| `base.py` | `ReportPlugin` ABC, `ReportResult` dataclass |
| `manager.py` | `ReportManager` — runs all plugins, isolates failures |
| `plugin_factory.py` | `ReportPluginFactory` — loads plugins from `[reports]` TOML config |
| `bundle.py` | `ReportBundleBuilder` — builds `ReportContext` from disk state |
| `file_report.py` | Writes signed JSON result file to `agent/memory/<game_id>/` |
| `gmail_report.py` | Sends report via Gmail API using OAuth credentials |
| `gatekeeper.py` | Rate-limits and validates LLM calls inside report generation |
| `delivery_store.py` | Idempotency guard — prevents duplicate email sends |

### 4.9 crewAI Agents (`agent/agents/`)

| Agent | Purpose |
|---|---|
| `StrategyAgent` | Selects the best move given observation and candidate actions |
| `GameManagerAgent` | Monitors game state, decides when to escalate |
| `ProtocolDiscoveryAgent` | Introspects opponent tools, verifies protocol flow |

Tools used by agents: `board_tool`, `protocol_tool`, `game_state_tool`, `strategy_tool`.

### 4.10 RL Subsystem (`agent/rl/`)

See `docs/PRD_rl.md` for full specification. Summary:

- `CopThiefEnv` — Gym-compatible simultaneous-action environment
- `PPOAgent`, `DQNAgent` — training agents
- `RLPolicy` — inference-only wrapper used by `GameOrchestrator._select_move_heuristic`

---

## 5. Interfaces

### 5.1 How `cop/__main__.py` uses `agent/`

```python
from agent.orchestrator import GameOrchestrator

orchestrator = GameOrchestrator(
    role="cop",
    secret=shared_secret,
    config_sha256=config_hash,
    games_dir=Path("agent/memory"),
    opponent_url="http://thief-host:5001/mcp",
    local_url="http://localhost:5000/mcp",
    group_name="team_alpha",
)
asyncio.run(orchestrator.run_async(host="0.0.0.0", port=5000))
```

### 5.2 How `thief/__main__.py` uses `agent/`

Identical pattern with `role="thief"`, swapped URLs, and port 5001.

### 5.3 How `webserver/` uses `agent/`

The webserver imports `GameRunner` only for in-process test games started from the GUI. For live inter-team games the webserver manages external agent processes and communicates with them over MCP rather than importing `GameOrchestrator` directly.

---

## 6. Constraints from Game Rules

| Constraint | Implementation |
|---|---|
| Separate processes — no shared memory | `GameOrchestrator.run_async` runs each agent as an independent OS process |
| Commit before reveal | `_handle_reveal` returns error if no stored commitment exists for the step |
| HMAC signing on every MCP message | `AgentMCPServer` verifies inbound; `GameMCPClient` signs outbound |
| Thief observes only last-revealed cop position | `thief_observation(last_revealed_cop_pos=...)` uses revealed position, not live board |
| Max turns enforced | `RulesEngine.check_game_status` returns `THIEF_WIN` when `board.turn >= max_steps` |
| Scent field is public to cop only | `cop_observation` includes scent channel; `thief_observation` does not |

---

## 7. Acceptance Criteria

1. Both `cop/__main__.py` and `thief/__main__.py` can import `GameOrchestrator` without errors.
2. `GameRunner` can run a complete game to a terminal outcome in tests.
3. All HMAC commitments verified by `final_audit` across a full game.
4. `RLPolicy` loads a `.pt` checkpoint and returns a valid move string.
5. Report plugins run after `game_end` without crashing the agent process.
6. All `agent/tests/` pass with `pytest agent/tests/`.
