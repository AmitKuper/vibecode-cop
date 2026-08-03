# Cop vs Thief — Cop Agent (vibecode-cop)

Companion repository: [vibecode-thief](https://github.com/amitKuper/vibecode-thief)

## Overview

A peer-to-peer Partially Observable cop-and-thief game implemented as a
Dec-POMDP (Decentralized Partially Observable Markov Decision Process).
Two independent OS processes communicate via FastMCP using a Commit-Reveal
protocol with cryptographic integrity and bilateral mutual audit.

## Dec-POMDP Model

Each agent observes only:
- its own position
- publicly placed barriers
- opponent scent field (decaying 5x5 Manhattan kernel)
- free-language hints from the opponent (possibly deceptive)

Hidden: opponent true position. Strategy decisions use a Bayesian belief
distribution over opponent position, updated via scent likelihood and
legal transition prediction.

## Architecture

```
PeerRuntime
  ├── ProtocolCoordinator  (16-state SM, single authority)
  ├── GameProtocolPort     (deterministic tool mapping, locked in Step-0)
  ├── StepJournal          (atomic per-step evidence, hash chain)
  ├── BeliefEngine         (Bayesian belief updates)
  ├── ScentFields          (symmetric cop_scent + thief_scent)
  ├── Gatekeeper           (Gmail rate-limiting pipeline)
  ├── DeadlineTracker      (bounded external requests)
  ├── LeagueLedger         (append-only match accounting)
  └── Watchdog             (independent OS-process freeze detection)
```

## RL Strategy

Primary movement: PPO policy receiving LocalObservation (no hidden coords).
Observation space: own position (one-hot), barriers, opponent scent,
belief heatmap, scalar features. Action space: N/S/E/W/STAY/PLACE_N/PLACE_S/PLACE_E/PLACE_W.
Legal action masking applied before sampling.

Heuristic baseline: pursuit agent (moves toward belief centroid).
Model status: infrastructure complete; trained checkpoint EXTERNAL_PENDING.

## Commit-Reveal Protocol

1. Step-0: bilateral signed declarations with Ed25519
2. COMMIT: both peers commit SHA-256(move||nonce) before revealing
3. REVEAL: simultaneous move reveal; mismatch -> technical loss
4. AUDIT: bilateral hash-chain transcript verification
5. RESULT: both sign identical ResultAgreement; bilateral Gmail send

## Installation

```bash
uv sync --frozen
uv run pytest tests/ agent/tests/ -q
```

## Usage

```bash
# Development (single machine)
uv run python -m agent.orchestrator_crew

# Counted series (requires real opponent)
uv run python scripts/run_series.py --counted --n-gamelets 6

# Live GUI
uv run uvicorn agent.gui.app:app --port 8080

# Replay viewer
uv run uvicorn agent.replay.app:app --port 8081
```

## Test Evidence

- Tests: 1095 passing, 0 failures
- Coverage: >=85% branch
- Ruff: 0 violations

## Limitations and External Evidence Required

- Real opponent match: EXTERNAL_PENDING
- Trained RL checkpoint: EXTERNAL_PENDING
- Gmail OAuth credentials: EXTERNAL_PENDING
- Public tunnel: EXTERNAL_PENDING
- Group ID (8-char): EXTERNAL_PENDING
- GUI screenshots: EXTERNAL_PENDING
