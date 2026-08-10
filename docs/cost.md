# Token Cost Tracking — vibecode-cop
**Per rules.md Rule 8**

## Methodology (honest limits)

All figures are **session-based estimates** — there is no per-call token
metering in this project. The aggregate anchor is **2,850,905 tokens**, the
number used by `notebooks/cost_sensitivity.ipynb`; the per-phase rows below are
coarse allocations of that aggregate to development phases, judged from session
counts and phase duration. Input/output split is not inferred (the design-phase
row's original estimate was ~250k input / ~80k output; later rows are tracked
as aggregates only). Every row is Estimated.

| Phase | Task | Tokens (aggregate) | Notes |
|---|---|---:|---|
| Pre-flight | Design + planning (all sessions) | ~330,000 | Estimated (~250k in / ~80k out) |
| Jul–Aug | Implementation + restructure (agent/ → cop_worker/league_manager, protocol, tests, config centralization) | ~1,500,000 | Estimated |
| ~2026-08-05..09 | RL research, book-model line (population-oracle distillation, DDQN/PSRO studies, harness audits) | ~600,000 | Estimated |
| 2026-08-09..10 | Chebyshev/minimax program + league games (search engine, from-scratch training, arena/archetype/A-B studies, imreeyal friendlies + counted series) | ~420,000 | Estimated |

## Cumulative Total

**~2,850,905 tokens** (all phases, Estimated) — reconciled with
`notebooks/cost_sensitivity.ipynb` `TOTAL_TOKENS`. Price sensitivity across
blended $/Mtok scenarios is computed in that notebook.

## Optimization strategies (why in-game cost is ~zero)

- **Template hints instead of LLM calls during play**: free-language hints in
  counted play are produced by templates, so a live series consumes **zero
  in-game tokens** (the counted driver's template-based deception replaced any
  per-move LLM call).
- **Local Ollama for generated hints** where richer language is wanted —
  local inference, no metered API tokens.
- **Deterministic search engine** (`hybrid_search` minimax) plays the sighted
  frames: move selection uses no model-inference tokens at all; the RL
  fallback is a local ~ms-scale PyTorch net.

Development tokens (the table above) dominate total cost; runtime cost per
match is effectively zero.
