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

## Quick Start

### Runtime Modes

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

Exact release artifact
`b9e74b7a13ca461484f2b47046eeecf8d393cb8d64b7cdd51d2915b714c21268`
captures 82.94% of 1,800 held-out gamelets, wins 99.33% of 300 exact
six-gamelet series, and clears the predeclared 55% worst-family floor at 57.78%.
Its official score is 31,395 versus 10,535 with zero technical failures and
0.371 ms p99 inference. Current learning curves, ten-family results, ablations,
sensitivity, curriculum comparison, and the analysis notebook are under
`results/rl/` and `notebooks/release_strategy_analysis.ipynb`.

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

The adaptive gate also launches the untouched published `reference-v3` league kit
in both call directions. Our deterministic adapter exposes its exact four-tool
surface, passes all 113 published vectors, locks the discovered profile before the
first commitment, and makes zero per-turn protocol-LLM calls.

## Known Limitations / EXTERNAL_PENDING

- Public tunnel and outside-opponent matches: EXTERNAL_PENDING
- Real Gmail OAuth delivery and provider message IDs: EXTERNAL_PENDING
- Actual eight-character course group ID: EXTERNAL_PENDING
- Official PDF/Moodle screenshots and individual submissions: EXTERNAL_PENDING
- Genuine Live GUI and Replay screenshots from the final external run: EXTERNAL_PENDING
- Final audited release tag push: EXTERNAL_PENDING

Local fake-Gmail output and localhost transport are acceptance evidence only; they
are never presented as real Gmail or public-network evidence.

## Configuration

- `config/game.json`: byte-identical canonical game and scoring values.
- `cop/config.toml`: role-local runtime, model, reporting, and timeout settings.
- `models/MANIFEST.json`: selected recurrent champion, checksum, schemas, and inference mode.
- Environment: `GROUP_ID` and runtime secrets are supplied outside Git. Gmail OAuth
  credentials remain local and must request only `gmail.send`.
- `--peer-url`: the thief MCP endpoint. Counted mode locks the negotiated profile
  before the first commitment.

## Module Reference

- `agent/role_cli.py`: package CLI and counted dependency preflight.
- `agent/agent_orchestrator.py`: sole counted subsystem composition root.
- `agent/adaptive/`: pre-game discovery, semantic mapping, conformance, and
  deterministic gameplay adaptation.
- `agent/domain/transition.py`: canonical authority for every physical action.
- `agent/rl/recurrent_policy.py`: checksum-verified inference and legal mask.
- `agent/peer_runtime*.py`: P2P lifecycle, audit, result, ledger, and reporting.
- `scripts/verify_100_readiness.py`: strict cross-repository release verifier.

## Troubleshooting

- **Counted mode rejects the worktree:** commit or intentionally remove local changes;
  counted provenance requires a clean, resolvable Git HEAD.
- **Champion fails to load:** run `uv sync --frozen` and compare the artifact
  SHA-256 with `models/MANIFEST.json`; counted mode never substitutes a heuristic.
- **Peer negotiation fails:** confirm the peer URL exposes SSE/MCP tools and inspect
  the incompatibility report; rejection before commitment is intentional.
- **Gmail fails:** keep send-only OAuth files outside Git. The fake-outbox option is
  local acceptance only and never evidence of real delivery.
- **A series aborts:** preserve both logs/audits and inspect the stable opponent's
  league entry before attempting another counted match.

## Project Structure

```text
agent/       orchestration, protocol, domain, RL, audit, reliability, reporting
cop/         role package CLI
config/      canonical and role-independent configuration
models/      tracked selected champion manifest and artifact
tests/       unit, integration, hostile, and production-lifecycle evidence
scripts/     series, evaluation, Gmail, replay, and strict verification tools
docs/        requirements, plans, ledger, cost, and external-action records
notebooks/   reproducible cost and sensitivity analysis
assets/      architecture and local illustrative captures (not external evidence)
results/     tournament and executable score evidence
```
