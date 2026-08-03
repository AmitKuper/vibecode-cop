# Phase 0 Spec Correction Report — vibecode-cop

**Date:** 2026-08-03  
**Baseline SHA:** `0e73947dc155a1d7b458cd85b1c1075659ecbd4d`

## Summary

Phase 0 corrected five binding-rule regressions that were present in the v0.5 baseline. All
corrections are verified by new acceptance tests in `tests/test_spec_corrections.py`.

---

## 0.1 Trapped-Thief Semantics

**Spec §3.4:** A thief with no orthogonal escape is captured — STAY does not count.

**Regression:** `check_game_status` used `get_legal_moves()` which includes STAY, so a
surrounded thief was never caught.

**Fix:**
- Added `Board.has_orthogonal_escape(role)` — checks only NORTH/SOUTH/EAST/WEST.
- `rules_outcomes.py` uses `has_orthogonal_escape("thief")` instead of legal-moves check.

**Tests:** `TestTrappedThiefSemantics` (7 tests) — all pass.

---

## 0.2 Barrier-on-Thief Capture

**Spec §5.2:** Placing a barrier on the thief's current cell consumes a barrier and ends the
game as COP_WIN.

**Regression:** `env_helpers.apply_place_action` had a guard that skipped placement when the
target cell matched the thief's position, preventing this legal capture move.

**Fix:** Removed the guard from `agent/rl/env_helpers.py`. Barrier-on-thief is now processed
normally; `Board.is_capture()` detects the overlap and reports COP_WIN.

**Tests:** `TestBarrierOnThiefCapture` (4 tests) — all pass.

---

## 0.3 Audit Completeness

**Spec §7.1:** An audit with zero opponent commits is NOT_APPLICABLE (not a counted match),
not a vacuous success.

**Regression:** `run_final_audit` returned `(True, {"audit_status": "PASSED"})` for empty
commitment logs, allowing zero-turn aborts to be counted as clean games.

**Fix:** `agent/peer_audit.py` — early-return `(False, {audit_status: NOT_APPLICABLE})` when
`h_commits` is empty. Non-empty audits produce `PASSED` or `FAILED` as before.

**Tests:** `TestAuditCompleteness` (3 tests) — all pass.

---

## 0.4 Exactly Six Gamelets

**League rule:** Counted series must have exactly six gamelets. Fewer or more is invalid.

**Regression:** `GameSeries.__init__` accepted any `n_gamelets` value in counted mode.

**Fix:**
- Added `COUNTED_GAMELETS = 6` module-level constant in `agent/game_series.py`.
- `GameSeries.__init__` raises `ValueError` when `not uncounted and n_gamelets != 6`.
- `scripts/run_series.py` rejects `--n-gamelets != 6` at the CLI level.
- Dev/test runs use `uncounted=True` to bypass the restriction.

**Tests:** `TestExactlySixGamelets` (7 tests) — all pass.

---

## 0.5 Movement / LLM Boundary

**Spec §6.1:** LLM agents provide hints and profiling only. Movement path is RL → heuristic.
LLM movement requires explicit Step-0 bilateral opt-in (`allow_llm_movement=true`).

**Regression:** `select_move` in `agent/peer_turn_helpers.py` fell through to
`_select_move_llm_async` when RL failed, making LLM a silent movement fallback.

**Fix:** `select_move` chain is now RL → heuristic (Board.get_legal_moves). `_select_move_llm_async`
is not called from the movement path.

**Tests:** `TestNoLLMMovementFallback` (2 tests) — all pass.

---

## 0.6 Mandatory UI Dependency

**Deliverable:** Live-view GUI is a mandatory deliverable; tests for it must always run.

**Regression:** `fastapi` was absent from production deps; `pytest.importorskip("fastapi")`
in `tests/test_live_gui_role_filtering.py` silently skipped 4 live-view tests.

**Fix:** `fastapi>=0.110` added to `[project.dependencies]` in `pyproject.toml`.
`pytest.importorskip` guard removed.

---

## 0.7 KNOWN_DEVIATIONS.md Corrected

Removed three false entries (DEV-002, DEV-003, DEV-005) and added a CORRECTED section
documenting what was fixed and why.

---

## Quality Gate Results

| Gate | Result |
|------|--------|
| pytest | 635 passed, 0 failed |
| branch coverage | 88% (≥85% required) |
| ruff check | All checks passed |
| ruff format | All files formatted |
