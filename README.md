# Cop vs Thief — Cop Agent

Companion: [vibecode-thief](https://github.com/amitKuper/vibecode-thief)

## System Architecture

```
counted CLI → AgentOrchestrator (single composition root)
  ├── RuntimeMode (COUNTED/WARMUP/DEVELOPMENT)
  ├── ProtocolCoordinator (16-state SM)
  ├── BeliefEngine (Bayesian belief updates)
  ├── ScentFields (symmetric cop/thief scent)
  ├── NaturalLanguagePolicy (deception strategy)
  ├── StepJournal (atomic evidence chain)
  ├── DeadlineTracker (bounded external requests)
  ├── Watchdog (independent OS process)
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
# Development (heuristic fallback is explicit and permitted)
uv run python -m cop series --mode development --peer-url <thief-mcp-url>

# Warmup (real transport, non-counted policy rules)
uv run python -m cop series --mode warmup --peer-url <thief-mcp-url>

# Counted (exactly six; requires a clean Git worktree and all production inputs)
uv run python -m cop series --mode counted --peer-url <thief-mcp-url> --secret <shared-secret>
```

The compatibility driver remains available as
`uv run python scripts/run_series.py --mode counted --thief-url <thief-mcp-url>`;
it resolves into the same counted composition and does not permit a non-six count.

## Strategy

Counted movement: `LocalObservation` + Bayesian `BeliefState` + recurrent history,
then the checksum-verified cop recurrent champion, legal-action mask, and canonical
domain validation. Missing or incompatible model evidence aborts counted mode.

Development/warmup movement may use the explicit belief heuristic baseline.
Action space: N/S/E/W/STAY/PLACE_N/PLACE_S/PLACE_E/PLACE_W (barrier placement for cop).
RL policy: tracked `RecurrentA2C-GRU` champion with paired held-out six-gamelet
promotion evidence in `results/cop_held_out_tournament.json`.
Language: `NaturalLanguagePolicy` with `DeceptionIntent` (TRUTH/LIE/AMBIGUOUS/BLUFF).

## Installation

```bash
uv sync --frozen
uv run python scripts/verify_100_readiness.py
```

## Live GUI / Replay

```bash
# Local-truth live view (no hidden opponent coords)
uv run uvicorn agent.gui.app:app --port 8080

# Replay with signed evidence verification
uv run uvicorn agent.replay.app:app --port 8081
```

## Verification Evidence

The strict verifier runs both complete suites with zero accepted skips, calculates
actual branch coverage (minimum 85% in each repository), checks Ruff and frozen
locks, validates both champion checksums and tournaments, runs hostile protocol,
tamper/replay, Watchdog and fake-Gmail suites, scans tracked files for secrets,
and launches the real isolated two-process six-gamelet counted path. A skipped or
failed code-verifiable gate makes the verifier fail.

## Known Limitations / EXTERNAL_PENDING

- Public tunnel and outside-opponent matches: EXTERNAL_PENDING
- Real Gmail OAuth delivery and provider message IDs: EXTERNAL_PENDING
- Actual eight-character course group ID: EXTERNAL_PENDING
- Official PDF/Moodle screenshots and individual submissions: EXTERNAL_PENDING
- Final audited release tag push: EXTERNAL_PENDING

Local fake-Gmail output and localhost transport are acceptance evidence only; they
are never presented as real Gmail or public-network evidence.
