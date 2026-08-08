# Implementation Plan — Cop Agent (vibecode-cop)
**Version:** 2.0 | **Group:** vibecode | **Date:** 2026-08-08

> Architecture authority: `docs/DESIGN.md` (3-process redesign). This plan describes
> the built structure of `vibecode-cop`, which ships **two** packages: `league_manager`
> (the match orchestrator / external MCP facade) and `cop_worker` (the cop role).

---

## 1. C4 Model

### Level 1 — System Context

```
┌─────────────────────────────────────────────────────────────────────┐
│                         External Actors                             │
│  [Opponent peer]      [Gmail API]        [Claude API]               │
│   (MCP over HTTP)     (result report)    (hints + belief only)      │
└───────┬───────────────────┬───────────────────┬────────────────────┘
        │                   │                   │
        ▼                   ▼                   ▼
┌───────────────────────────────────────────────────────────────────┐
│                         vibecode product                          │
│  LeagueManager  +  Cop Worker  +  Thief Worker (vibecode-thief)    │
│  Autonomous P2P cops-and-robbers: signed Step-0, commit-reveal,   │
│  six gamelets, RL movement, mutual audit. No central referee.     │
└───────────────────────────────────────────────────────────────────┘
```

### Level 2 — Container Diagram (3 processes)

```
                     opponent peer (MCP/HTTP)
                              │
                              ▼
┌───────────────────────────────────────────────────────────┐
│  LeagueManager  (vibecode-cop, external MCP :61222)         │
│  admin_api (:8080)  router  worker_lifecycle                │
│  series_lifecycle   protocol/ (ref-v3 adapter, detection)   │
│  reports/ + gmail/  step0/series_declaration  league_ledger │
│  — terminates transport, routes each sub-game to a worker,  │
│    owns NO game semantics —                                 │
└───────────┬───────────────────────────────┬────────────────┘
            │ internal MCP (:8001)           │ internal MCP (:8002)
            ▼                                ▼
┌────────────────────────┐        ┌────────────────────────────┐
│  Cop Worker            │        │  Thief Worker               │
│  (vibecode-cop)        │        │  (vibecode-thief)           │
│  cop_worker/           │        │  thief_worker/              │
│  owns cop game         │        │  owns thief game semantics  │
│  semantics             │        └────────────────────────────┘
└────────────────────────┘
```

A peer may also connect **directly** to a worker's MCP port (cop `:61224`,
thief `:61223`) in the direct topology — see `docs/DEPLOYMENT_TUNNEL_RUNBOOK.md`.

### Level 3 — Component Diagram (Cop Worker)

```
┌──────────────────────────────────────────────────────────────────────┐
│  cop/__main__.py  →  cop_worker/__main__.py                          │
│  ┌─────────────────────────────┐  ┌───────────────────────────────┐  │
│  │ MCP layer                   │  │ Game semantics                │  │
│  │ mcp_server.py               │  │ gamelet.py (owns a sub-game)  │  │
│  │ mcp/server_handlers.py      │  │ state_machine.py (lifecycle)  │  │
│  │ mcp/coordinator.py          │  │ commit_reveal.py (protocol SM)│  │
│  │ mcp/protocol*, client.py    │  │ rules_engine / board / scent  │  │
│  └─────────────────────────────┘  │ observation / belief_engine   │  │
│  ┌─────────────────────────────┐  │ parameter_registry.py         │  │
│  │ Strategy                    │  └───────────────────────────────┘  │
│  │ rl/ (RecurrentA2C-GRU)      │  ┌───────────────────────────────┐  │
│  │ + deterministic heuristic   │  │ Integrity                     │  │
│  │ language/ (free-text hints) │  │ crypto.py (commit/sign)       │  │
│  └─────────────────────────────┘  │ audit/ (result_consensus)     │  │
│                                    │ step0/ (declaration, signing) │  │
│                                    │ gmail/ (gatekeeper, sender)   │  │
│                                    └───────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 2. Match Lifecycle

```
CLI: python -m league_manager --counted --port 61222
  → LeagueManager starts, auto-spawns cop_worker + thief_worker (worker_lifecycle)
  → signed bilateral Step-0 (step0/series_declaration + worker gamelet declarations)
  → protocol detection / ref-v3 adapter locks a profile (protocol/)
  → six gamelets, role schedule {1:cop,2:thief,3:cop,4:thief,5:cop,6:thief}
      each gamelet: LM routes tool calls → worker commit-reveal loop
        commit (SHA-256) → ack → reveal → verify → apply → check terminal
  → mutual comprehensive audit → signed result consensus (audit/result_consensus)
  → league_ledger update → independent Gmail reports → DONE
```

---

## 3. Cop Movement Selection

```
select_move():
  1. RL path (primary): MANIFEST-pinned RecurrentA2C-GRU champion, legal-action masked
  2. Deterministic heuristic fallback: minimise Chebyshev(cop_pos, scent_peak),
     respecting legal-move + barrier masks
```

Free-language hints and the belief-map update may use a direct Claude call
(`cop_worker/language/`, `cop_worker/llm/`); the LLM never drives the movement choice.
There is **no CrewAI / agent framework.**

---

## 4. Design Decisions

### AD-1: No Central Judge (P2P)
Each side independently verifies game state via commit-reveal; disagreement →
TECHNICAL_LOSS. The LeagueManager terminates transport and routes, but is **not** a
referee — it owns no game semantics (`league_manager/router.py`).

### AD-2: SHA-256 Commit-Reveal
Neither side can choose a move after seeing the opponent's. Commitment payload includes
`{game_id, gamelet, step, role, state_hash, move, hint, intent, nonce}`; the `gamelet`
field prevents cross-gamelet replay (`cop_worker/commit_reveal.py`, `crypto.py`).

### AD-3: LeagueManager as Facade, not Game Owner
One stable external URL for all six sub-games; workers remain autonomous P2P agents.
Boundary: LM = transport/routing; worker = game protocol semantics (DESIGN Decisions 2–5).

### AD-4: Signed Bilateral Step-0 + Mutual Audit
Each side publishes a signed declaration (hardware, model SHA, git SHA, config SHA) and
the match ends only on signed result consensus (`step0/`, `audit/result_consensus.py`).

### AD-5: Scent Field for Cop Observation
`scent = 0.9 × 0.10^(chebyshev(cop, thief_last))` — directional signal without exact
position (`cop_worker/scent.py`, `observation.py`).

### AD-6: RL Movement, No Framework
Movement is a recurrent RL policy (local observation + Bayesian belief); the only LLM
use is free-text hints and belief updates.

---

## 5. Technology Stack

| Component | Library | Purpose |
|-----------|---------|---------|
| MCP transport | MCP over HTTP | worker servers + LM facade / peer calls |
| LLM (hints/belief only) | `anthropic` | free-language hints, belief-map updates |
| RL | `torch` | RecurrentA2C-GRU policy networks |
| Gmail reporting | `google-api-python-client` | OAuth 2.0 `gmail.send` |
| Package mgmt | `uv` | dependency resolution (`uv sync --frozen`) |
| Testing | `pytest` | fast suite, no LLM / no network |
| Linting | `ruff` | zero violations enforced |

---

## 6. File Structure (vibecode-cop)

```
cop/__main__.py            ← thin entry; delegates to cop_worker
cop_worker/                ← cop role (internal MCP server)
├── __main__.py            ← worker CLI (serve on --port)
├── mcp_server.py, mcp/    ← MCP server + handlers, coordinator, protocol, client
├── gamelet.py             ← one sub-game's semantics
├── state_machine.py       ← gamelet lifecycle state machine
├── commit_reveal.py       ← commit-reveal protocol state machine
├── rules_engine.py, board.py, rules_outcomes.py
├── scent.py, observation*.py, belief_engine.py, synthetic_belief.py
├── parameter_registry.py  ← binding/fixed/negotiated term enforcement
├── crypto.py              ← canonical JSON, commitments, signing
├── rl/                    ← recurrent policy, networks, heuristics, env
├── language/, llm/        ← free-text hints + Claude client (non-movement)
├── audit/                 ← result_consensus, audit_summary, step_journal
├── step0/                 ← signed gamelet declaration + signing
├── gmail/                 ← gatekeeper, sender, quota/DOS/circuit-breaker
├── config/, reliability/, protocol/, replay/, gui/
league_manager/            ← match orchestrator / external MCP facade
├── __main__.py            ← `python -m league_manager --counted --port 61222`
├── admin_api.py           ← localhost control HTTP (:8080)
├── router.py              ← routes ref-v3 calls to the correct worker (identity only)
├── worker_lifecycle.py    ← spawns/monitors cop & thief worker subprocesses
├── series_lifecycle.py, series_jsonl.py  ← six-gamelet series + JSONL events
├── peer_topology.py       ← single-address / role-split topology handling
├── protocol/              ← ref-v3 adapter, detection, transport probe, pipeline
├── reports/, gmail/       ← league result composition + gated Gmail send
├── step0/                 ← series-level signed declaration
├── league_ledger.py       ← cross-series ledger
└── config/, reliability/
```
