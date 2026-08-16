# Plan — Live GUI and Replay Viewer (cop repo)

See GUI_PRD.md for requirements, GUI_TODO.md for live status.

## Architecture (unchanged foundations)

- `cop_worker/gui/app.py` — FastAPI app: `/` live page, `/api/view`, `/api/stream`
  (SSE). Gains `/replay` + `/api/replay/*`.
- `cop_worker/gui/live_view_model.py` — thread-safe `LiveViewModel`; re-verifies no
  hidden coordinate on every update.
- `cop_worker/observation.py::SafeLiveView` — the ONLY payload the GUI ever sees.
- `scripts/ref3_match/gui_bridge.py` — worker-side glue: `maybe_start_gui`
  (init carries `gui_port`), `publish_view` (fire-and-forget), `stop_gui`.
- Runtime note: in a production split match both role workers execute the cop
  repo's copy of this byte-identical code; this repo's copy serves standalone
  runs and keeps the repo self-contained (see docs/KNOWN_DEVIATIONS.md on
  cross-repo duplication).

## Work packages

### WP1 — View model carries the full local truth
Extend `SafeLiveView` with: `sub_game`, `max_steps`, `num_sub_games`,
`opponent_group`, `audits` (list of per-window verdicts), `last_commit_sent`,
`last_commit_received` (12-char prefixes). Distinguish belief vs scent inputs
in `publish_view` (today the scent grid doubles as both). Wire real values:
hint text, your_turn from the turn loop, score so far, gamelet number.
Leak-verify unchanged + extended test.

### WP2 — Live page with the five panels
Single static HTML (no build step): header + banner (A), belief heatmap (B),
sensed scent (C), hint strip (D), integrity ticker (E). SSE-driven; degrades to
polling `/api/view`.

### WP3 — Shared replay verification core
`cop_worker/replay/verify.py`: load a `log_*.json`, recompute
`SHA256(canonical_json(payload)+"|"+nonce)` per record vs stored commit,
yield per-step verdicts + whole-log verdict. Used by BOTH frontends.

### WP4 — CLI stepping
`scripts/replay_viewer.py`: keep one-shot mode; add `--interactive` (n/p/j/q)
showing per-step payload, recomputed vs stored hash, running verdict.

### WP5 — Web replay page
`/replay`: pick a log from `results/`, slider over steps, our-side board
reconstruction, per-step + final `Verified OK / TAMPERED` banner.

### WP6 — Always-on defaults + fail-open hardening
Uncomment `gui_cop_port = 8781` in config/runtime.toml (both roles in the
cop repo's base config). Busy port => logged skip. Publish already guarded.

### WP7 — Tests
- test_gui_local_truth_series: full sim series, assert no hidden coordinate in
  any published view.
- test_gui_fail_open: GUI task killed mid-window; series settles 6/6.
- test_replay_verdicts: pristine real log => Verified OK; 1-byte tamper =>
  TAMPERED (CLI core + web endpoint).
- Strength check: GUI-on series result == GUI-off baseline.

### WP8 — Evidence + docs
Screenshots (live heatmap mid-game + replay Verified OK on a real counted log)
into evidence/; update README + KNOWN_DEVIATIONS (screenshot deviation closes);
mirror everything byte-identical to the sibling repo; add new shared modules to
scripts/check_shared_drift.py.

## Order: WP1 -> WP2 -> WP3 -> WP4 -> WP5 -> WP6 -> WP7 -> WP8
