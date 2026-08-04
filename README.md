# Cop vs Thief — Cop Agent

Companion: [vibecode-thief](https://github.com/amitKuper/vibecode-thief)

## System Architecture

```
AgentOrchestrator (single composition root)
  ├── RuntimeMode (COUNTED/WARMUP/DEVELOPMENT)
  ├── ProtocolCoordinator (16-state SM)
  ├── BeliefEngine (Bayesian belief updates)
  ├── ScentFields (symmetric cop/thief scent)
  ├── NaturalLanguagePolicy (deception strategy)
  ├── StepJournal (atomic evidence chain)
  ├── DeadlineTracker (bounded external requests)
  ├── Watchdog (independent OS process — DEVELOPMENT skipped)
  ├── LeagueLedger (counted-match accounting)
  ├── LiveViewModel (SafeLiveView — no hidden coords)
  └── Gatekeeper (Gmail pipeline, production only)
```

## Dec-POMDP Information Model

Each agent observes ONLY:
- own true position
- public barriers
- opponent scent field (decaying 5×5 radial kernel)
- free-language hints (possibly deceptive)
- Bayesian belief heatmap over opponent position

Hidden: opponent true position. `build_local_observation()` enforces this.

## Runtime Modes

```bash
# Development (default — safe fallbacks, no model validation)
uv run python scripts/run_series.py

# Warmup (real transport, guards relaxed)
uv run python scripts/run_series.py --mode warmup --thief-url <url>

# Counted (fail-closed — rejects dev secrets, placeholder models, etc.)
uv run python scripts/run_series.py --mode counted --thief-url <url>
```

## Strategy

Movement: belief-driven heuristic (pursuit toward belief centroid) in DEVELOPMENT/WARMUP.
Action space: N/S/E/W/STAY/PLACE_N/PLACE_S/PLACE_E/PLACE_W (barrier placement for cop).
RL policy: infrastructure complete, training EXTERNAL_PENDING.
Language: `NaturalLanguagePolicy` with `DeceptionIntent` (TRUTH/LIE/AMBIGUOUS/BLUFF).

## Installation

```bash
uv sync --frozen
uv run pytest tests/ agent/tests/ -q
```

## Live GUI / Replay

```bash
# Local-truth live view (no hidden opponent coords)
uv run uvicorn agent.gui.app:app --port 8080

# Replay with signed evidence verification
uv run uvicorn agent.replay.app:app --port 8081
```

## Test Evidence

- Cop tests: 1173 passing, 0 failures
- Coverage: >=85% branch
- Ruff: 0 violations

## Known Limitations / EXTERNAL_PENDING

- RL model training: EXTERNAL_PENDING (infrastructure complete, weights are placeholder-initialized)
- Public tunnel match: EXTERNAL_PENDING
- Gmail OAuth credentials: EXTERNAL_PENDING
- Real bilateral audit in production: EXTERNAL_PENDING (components wired, not exercised end-to-end)
- GUI screenshots: placeholder 1×1 PNGs (real screenshots require browser session)
- Group ID (8-char): EXTERNAL_PENDING
