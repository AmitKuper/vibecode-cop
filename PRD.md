# PRD.md — superseded

Canonical documents live in `docs/`: see [`docs/PRD.md`](docs/PRD.md) plus the
per-component PRDs — [`docs/PRD_cop_worker.md`](docs/PRD_cop_worker.md),
[`docs/PRD_league_manager.md`](docs/PRD_league_manager.md) and
[`docs/PRD_search_engine.md`](docs/PRD_search_engine.md). This stub is kept so
old links resolve.

Current state: cop_worker + league_manager architecture, reference-v3 wire,
split (one process per role) production runtime, `hybrid_search` move engine
(minimax over exact chebyshev tracking, RL fallback). Five counted series played
(`results/counted_series.json`): lost 35–75 vs anrbj666, then won 90–30 vs
imreeyal, uoh-sqak, rstabcde and najamjad — 6/6 audits Verified OK each.
