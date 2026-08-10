# PLAN.md — superseded

Canonical documents live in `docs/`: the architecture authority is
[`docs/DESIGN.md`](docs/DESIGN.md) (C4 + sequence diagrams, numbered
architecture decisions); historical planning is in [`docs/PLAN.md`](docs/PLAN.md).
This stub is kept so old links resolve.

Current state: one match-runner process (`scripts/live_match_ref3.py`) serves
both MCP endpoints (cop 61224, thief 61223) and plays six sub-games over
reference-v3 (commit-reveal, mutual audit). The `agent/`-era design this file
once described is dead and being deleted.
