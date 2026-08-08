# Product Requirements Document — Cop Agent (vibecode-cop)
**Version:** 2.0 | **Group:** vibecode | **Date:** 2026-08-08

> Architecture authority: `docs/DESIGN.md` (3-process redesign). This PRD describes
> the cop side of the distributed cops-and-robbers product as it is actually built.

---

## 1. Role Overview

The **Cop Agent** is one half of a fully decentralized P2P multi-agent game. Its
objective is to **capture the thief** — to occupy the same cell as the thief within
35 moves per gamelet. Over a series of six gamelets the sides accumulate score.

The cop role runs as the **`cop_worker`** process — an autonomous MCP server that
owns all cop-side game semantics. In a full match it is coordinated by the
**LeagueManager** (the single external-facing process); a peer may reach it either
through the LeagueManager facade or, in the direct topology, by connecting to the
cop worker's MCP port (see `docs/DEPLOYMENT_TUNNEL_RUNBOOK.md`). Either way the
`cop_worker`:
- Runs as an MCP server exposing the worker control tools
- Independently verifies every move commitment from the thief (commit-reveal)
- Applies game rules locally without a central referee
- Observes the board through a **scent field** (Chebyshev-distance decay from the
  thief's last known position) — never the thief's true position

### Strategic Objective
Hunt the thief across a 7×7 grid, using scent-field signals, barrier placement, and a
learned recurrent RL policy to close distance efficiently, balancing aggressive
pursuit against the risk of being evaded.

---

## 2. Acceptance Criteria

| # | Criterion | Verification |
|---|-----------|--------------|
| AC1 | Cop role runs as its own `cop_worker` process; a full match is 3 processes (LeagueManager + cop_worker + thief_worker) with no shared live state | Separate PIDs; workers own game state, LM owns only transport/routing |
| AC2 | `cop_worker` is an MCP server reachable via the LM facade **or** directly on its worker port | Both connection topologies exercised (DEPLOYMENT runbook) |
| AC3 | Cop's commitment hash matches SHA-256 of canonical JSON at final audit | Commit-reveal + tamper-detection tests in the suite |
| AC4 | Cop observation never contains the thief's true position | Observation/no-leak tests in the suite |
| AC5 | Exactly six gamelets run per series; scores aggregate correctly | Series-lifecycle tests; `num_games` is a FIXED term = 6 |
| AC6 | Watchdog / deadline expiry causes TECHNICAL_LOSS | Deadline-tracker tests |
| AC7 | Shared game config is SHA-256 validated at game start | Config-conformance tests |
| AC8 | Gmail sends use only the `gmail.send` scope, gated by counted-mode | Gatekeeper tests; OAuth token inspection |
| AC9 | Suite green with zero Ruff violations, ≥85% coverage | `uv run pytest`, `uv run ruff check .` |

---

## 3. User Stories (Cop Perspective)

### Cop Worker
- **As the cop worker**, I want a scent field approximating thief proximity so I can
  plan moves without seeing the thief's exact position (fair information asymmetry).
- **As the cop worker**, I want every move I commit to be cryptographically signed so
  the thief cannot claim I changed my move after seeing theirs.
- **As the cop worker**, I want the thief's reveal verified against their earlier
  commitment so I can detect a tampered move and trigger a TECHNICAL_LOSS.
- **As the cop worker**, I want a deterministic heuristic fallback when the trained RL
  model is unavailable so I can still play a legal game.
- **As the cop worker**, I want my per-gamelet report written to disk so any auditor
  can verify my move history offline.

### League Administrator
- **As a league administrator**, I want six gamelets per match with aggregate scoring
  so individual luck is averaged over a series.
- **As a league administrator**, I want both sides to compute the same config hash so I
  can confirm they played under identical parameters.

### Security Auditor
- **As a security reviewer**, I want the shared config SHA-256 locked so neither side
  can unilaterally change agreed parameters mid-match.
- **As a compliance officer**, I want credentials and tokens excluded from git history
  so the OAuth secret is never exposed.

---

## 4. Functional Requirements

### FR-1: Board & Movement
- FR-1.1: 7×7 grid, origin top-left, 0-indexed. Cop starts at `cop_start` (default `[0,0]`).
- FR-1.2: Legal moves are N, S, E, W, STAY. Diagonal moves are forbidden.
- FR-1.3: Out-of-bounds moves are rejected; the cop stays in place.
- FR-1.4: The cop may place up to 14 barriers per game; a barrier blocks entry to a cell.
- FR-1.5: Maximum 35 moves per gamelet (`survival_threshold = 35`).

### FR-2: Win Conditions (cop's perspective)
- FR-2.1: **Cop wins** when cop and thief occupy the same cell after a move.
- FR-2.2: **Cop loses** the gamelet when the thief survives to the move limit.
- FR-2.3: **TECHNICAL_LOSS** (cop scores 0) when audit fails or the deadline expires.

### FR-3: Scoring
Scoring values are loaded from the shared game config at runtime; capture rewards the
cop, survival rewards the thief, ties split, and a TECHNICAL_LOSS scores 0.

### FR-4: Commit-Reveal Protocol (cop's responsibilities)
- FR-4.1: Cop commits before revealing its move each turn.
- FR-4.2: Commitment = `SHA-256(canonical_json({game_id, gamelet, step, role, state_hash, move, hint, intent, nonce}))`.
- FR-4.3: The `gamelet` field prevents cross-gamelet replay.
- FR-4.4: Cop verifies the thief's reveal matches the thief's earlier commitment.
- FR-4.5: Mismatch → cop declares TECHNICAL_LOSS for the thief and logs the abort reason.

### FR-5: Hidden Information (cop's observation)
- FR-5.1: The cop observation carries a scent field (Chebyshev-distance decay from the
  thief's last known position) — never the thief's true position.
- FR-5.2: `scent = center_intensity × decay^(chebyshev_distance)`, with
  `center_intensity = 0.9`, `decay = 0.10`.

### FR-6: Shared Configuration
- FR-6.1: The shared game config is the single source of truth for agreed parameters.
- FR-6.2: Cop embeds the config SHA-256 in every protocol message.
- FR-6.3: Binding/fixed terms (e.g. `diagonal_moves=false`, pheromone constants,
  `num_games=6`) and minimum terms (`max_barriers≥14`, `survival_threshold≥35`) are
  enforced by the parameter registry.

### FR-7: Six-Gamelet Series
- FR-7.1: A full match runs exactly 6 gamelets sequentially.
- FR-7.2: Scores accumulate per gamelet; the series winner has the higher total.

### FR-8: Reporting
- FR-8.1: After each gamelet the cop writes structured per-gamelet reports (config,
  log, result, signed declaration with hardware / model / git SHA / config SHA).
- FR-8.2: Gmail reporting uses OAuth 2.0 with `gmail.send` scope only. During
  development, reports go to the owner's test inbox (`agentsorch@gmail.com`); a counted
  match reports the structured result to the course address
  (`rmisegal+uoh26finalgame@gmail.com` via LeagueManager config). See
  `docs/GMAIL_REPORTING_RUNBOOK.md`.

### FR-9: Replay & Audit
- FR-9.1: Cop log files carry SHA-256 integrity so any gamelet can be audited offline.
- FR-9.2: Final bilateral audit must reach signed consensus before a result is reported.

### FR-10: Network Resilience
- FR-10.1: Every protocol call is bounded by a response timeout.
- FR-10.2: Each turn is bounded by a watchdog/deadline.
- FR-10.3: Timeout expiry triggers TECHNICAL_LOSS and terminates the game.

---

## 5. Non-Functional Requirements

| Category | Requirement |
|----------|-------------|
| **Latency** | RL-path turn latency well under the move deadline (p99 ~12 ms observed) |
| **Reliability** | Watchdog prevents infinite hangs; retry logic handles transient network failures |
| **Security** | Credentials never committed; every protocol message is signed |
| **Maintainability** | Max 150 lines per file; zero Ruff violations; ≥85% test coverage |
| **Auditability** | Any cop log file can be verified offline without replaying the game |
| **Portability** | Runs on Windows, macOS, Linux; Python 3.12+; managed via `uv` |

---

## 6. Strategy Component PRD

### 6.1 Cop Movement Policy

Movement is **algorithmic/RL**, not LLM-driven (no CrewAI / no agent framework). The
strategy pipeline is:

```
1. RL path (primary): recurrent policy loaded from models/ (MANIFEST-pinned champion)
2. Deterministic heuristic fallback: minimise Chebyshev distance to the scent peak,
   respecting legal-move and barrier masks
```

Free-language hints and the belief-map update are the only operations that may use a
direct LLM call; they never drive the movement decision.

**RL policy.** The deployed champion is a **RecurrentA2C-GRU** policy trained on
local observations plus a Bayesian belief map (grid 7, hidden size 128), pinned in
`models/MANIFEST.json` by SHA-256 (current cop champion win rate ≈ 0.833). Inference
applies a mandatory legal-action mask.

**Scent field.** The observation includes a 7×7 scent field
`scent = 0.9 × 0.10^(chebyshev_dist(cop_pos, thief_last_pos))` — a noisy directional
signal (0.9 at distance 0, 0.09 at distance 1, 0.009 at distance 2). The observation
never includes the thief's raw coordinates.

**Action space.** Cop has **9 discrete actions**:
`{N, S, E, W, STAY, PLACE_N, PLACE_S, PLACE_E, PLACE_W}` — five moves plus four
directional barrier placements. Illegal actions are masked to STAY. (The thief action
space omits the barrier actions — the thief never places barriers.)
