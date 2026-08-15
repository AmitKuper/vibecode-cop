# TODO.md — superseded

The canonical task list is [`docs/TODO.md`](docs/TODO.md); accepted deviations
are recorded in [`docs/KNOWN_DEVIATIONS.md`](docs/KNOWN_DEVIATIONS.md). This
stub is kept so old links resolve.

Current state: all code-verifiable gates pass (ruff clean; 1,887 tests passing,
4 environment-conditional skips; 94.90% branch coverage against a CI gate of 94).
Five counted series are played and settled (`results/counted_series.json`): lost
35–75 vs anrbj666 with the old pure-RL engine, then won 90–30 vs imreeyal,
uoh-sqak, rstabcde and najamjad with `hybrid_search`. Remaining work is the
external submission steps plus the post-league refactors (module dedup, the last
seven over-150-line files).
