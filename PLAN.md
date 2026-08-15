# PLAN.md — superseded

Canonical documents live in `docs/`: the architecture authority is
[`docs/DESIGN.md`](docs/DESIGN.md) (C4 + sequence diagrams, numbered
architecture decisions); the implementation plan is
[`docs/PLAN.md`](docs/PLAN.md). This stub is kept so old links resolve.

Current state: production runs `--arch split` — the orchestrator
(`scripts/ref3_match/series_split.py`) spawns one OS process per role via
`scripts/ref3_role_worker.py` (cop `:61224`, thief `:61223`), and the six
sub-games are played over reference-v3 with commit-reveal and mutual audit.
Five counted series are settled (`results/counted_series.json`).
