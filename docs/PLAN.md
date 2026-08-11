# Implementation Plan — Cop Agent (vibecode-cop)
**Version:** 2.1 | **Group:** vibecode | **Date:** 2026-08-12

> Architecture authority: `docs/DESIGN.md`. **Production runtime is one process**:
> `scripts/live_match_ref3.py` serves both roles (cop `:61224`, thief `:61223`) and
> drives the whole series (DESIGN AD-1). The repo still ships **two** packages —
> `cop_worker` (game semantics, RL, language) and `league_manager` (ledger, reports,
> routing) — which the runner uses as libraries; their 3-process
> LeagueManager+worker composition survives only as a **simulation/dev harness**.

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
│  Match runner (live_match_ref3) + cop_worker + thief model repo   │
│  Autonomous P2P cops-and-robbers: signed Step-0, commit-reveal,   │
│  six sub-games, minimax/RL movement, mutual audit. No referee.    │
└───────────────────────────────────────────────────────────────────┘
```

### Level 2 — Container Diagram

**Production** — one match-runner process, both roles (DESIGN AD-1):

```
                     opponent peer (MCP/HTTP)
                       │                  │
                       ▼                  ▼
┌────────────────────────────────────────────────────────────┐
│  Match runner  scripts/live_match_ref3.py  (one process)   │
│  cop MCP endpoint :61224      thief MCP endpoint :61223    │
│  Step-0 negotiate → sealed turns → mutual audit → settle   │
│  libraries: cop_worker/ (protocol, domain, RL, language),  │
│  league_manager/ (ledger, reports), gmail pipeline,        │
│  models/MANIFEST.json, config/ profiles, artifacts/        │
└────────────────────────────────────────────────────────────┘
```

Both ports are bound by the runner itself (static public IP, router
port-forwarding, no tunnel).

**Simulation / dev harness only** — the 3-process composition below still runs
(`python -m league_manager`) but is **not** the production path:

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

In production the peer connects **directly** to `:61224`/`:61223`, which the
match runner binds — see `docs/DEPLOYMENT_TUNNEL_RUNBOOK.md` for the network path.

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

## 2. Match Lifecycle (production)

```
CLI: python scripts/live_match_ref3.py --match --config <opp> [--counted --report-to <addr>]
  → one match-runner process binds cop :61224 + thief :61223, dials the peer
  → per sub-game: signed Step-0 negotiate (flat terms, scent/wire locks, game_uid)
  → six sub-games, role schedule {1:cop,2:thief,3:cop,4:thief,5:cop,6:thief}
      sealed turns (commit-reveal): thief first, cop replies; hint attached
  → mutual comprehensive audit per sub-game (reveal + rehash every commit)
  → settlement → artifacts + league ledger → Gmail report
    (friendly: own inbox; counted: --report-to, passed by hand) → DONE
```

The dev-harness lifecycle (`python -m league_manager --counted --port 61222`,
auto-spawned workers, LM routing) exercises the same packages in simulation but
is not the counted path.

---

## 3. Cop Movement Selection

```
select_move()  (--move-policy hybrid_search, the shipped default vs imreeyal):
  1. Exact fix from the chebyshev frame (0.8-peak oracle) → depth-limited
     minimax with territory evaluation (DESIGN AD-3, AD-4)
  2. Blind/ambiguous frame → MANIFEST-pinned RL champion, legal-action masked
--move-policy rl serves the RL path alone (byte-identical fallback net).
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

### AD-3: LeagueManager as Facade, not Game Owner (dev harness)
One stable external URL for all six sub-games; workers remain autonomous P2P agents.
Boundary: LM = transport/routing; worker = game protocol semantics. In production
the LM process does not run — the match runner uses `league_manager/` as a library
(ledger, reports) per DESIGN AD-1.

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
scripts/live_match_ref3.py ← PRODUCTION match runner: both roles, one process (DESIGN AD-1)
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
league_manager/            ← routing facade (dev harness) + ledger/report libraries
├── __main__.py            ← `python -m league_manager --counted --port 61222` (simulation)
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
