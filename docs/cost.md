# Resource, token, and cost analysis

This ledger covers both repositories as one distributed product; do not add the two
copies together.

## Counted runtime

Movement inference is local PyTorch CPU inference. The final held-out gates measured:

| Role | p50 | p95 | p99 | Technical failures |
|---|---:|---:|---:|---:|
| Cop | 0.234 ms | 0.307 ms | 0.371 ms | 0 |
| Thief | 0.254 ms | 0.331 ms | 0.403 ms | 0 |

The deterministic MCP adapter makes zero per-turn LLM calls. The default language
realizer is template-based, so its counted token/API cost is zero. If an optional LLM
realizer is configured, its provider usage must be measured separately and is not
included here.

## Local training and evaluation resources

The final evidence was produced on Windows 11, Intel64 Family 6 Model 158, Python
3.13.14, PyTorch 2.13.0+cpu, and NumPy 2.5.1. No GPU or paid training service was
used. The exact-checkpoint ablation matrix took 261.51 seconds for cop and 289.74
seconds for thief on this host. Each final role tournament evaluated 1,800 candidate
gamelets plus the paired 1,800-gamelet heuristic baseline.

Checkpoints are compact CPU artifacts. Training uses only local observations and
stored historical checkpoints; it has no data-acquisition or external API cost.

## Token and currency accounting

The execution environment does not expose a trustworthy input/output-token billing
split for this Code-100 run. Therefore no currency total is asserted. The notebook
at `notebooks/cost_sensitivity.ipynb` accepts user-supplied token counts and prices;
it does not embed or claim a provider rate.

Machine-readable runtime metadata is in
`results/rl/strategy_analysis.json`. Any external tunnel, Gmail, Moodle, or
cross-group activity remains `EXTERNAL_PENDING` and has no fabricated cost entry.
