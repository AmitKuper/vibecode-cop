# Test Evidence — vibecode-cop

## Phase 0 baseline (2026-08-02)

### Environment

| Item | Value |
|------|-------|
| Python | 3.13.14 |
| Platform | Windows 11 Pro 10.0.26200 |
| pytest | 9.1.1 |
| Baseline SHA | 0fd1c208d0955a0eb915153ec6336734a674684a |
| Phase-0 SHA | e77d23a (fix: circular import + startup tests) |

### Startup smoke tests (Phase 0)

Command: `uv run pytest tests/test_startup.py -v`

Result: **5 passed in 22.55s**

All subprocess-level entry-point imports verified clean:
- `import agent.peer_agent_runtime` — PASS
- `import cop.__main__` — PASS
- combined import — PASS
- `scripts/run_series.py --help` — PASS
- `agent.language.hints.generate_hint` — PASS

### Full test suite baseline

Command: `uv run pytest tests/ agent/tests/ --tb=no -q`

Result: **549 passed, 58 failed, 33 warnings** in 78.80s

#### Failure classification

| Category | Count | Example |
|----------|-------|---------|
| Stale scent-decay expectation (additive accumulates > 0.9) | 1 | `test_compliance.py::...` — asserts `< 0.9` but additive model reaches 1.43; will be resolved in Phase 3 with KNOWN_DEVIATIONS |
| RL model channel mismatch (5-channel obs vs 4-channel checkpoint) | ~5 | `RuntimeError: mat1 and mat2 shapes cannot be multiplied (1x245 and 196x128)` |
| `fastapi` not installed (webserver/live-view tests) | ~5 | `ModuleNotFoundError: No module named 'fastapi'` |
| Stale game-rule test (barrier-on-thief now triggers COP_WIN earlier) | ~2 | `assert <GameOutcome.COP_WIN> == <GameOutcome.ONGOING>` |
| Stale crewAI/LLM behavior expectation | ~8 | `assert 'SOUTH' == 'N'` |
| Missing `opponent_commitments.json` in empty-audit test | 1 | `assert False is True` — pre-existing |
| `test_rl_tools_reports.py` CrewAI factory tests | 18 | Missing CrewAI agents/tasks not yet implemented |
| Other pre-existing environment/external | ~18 | Various |

None of the 58 failures were introduced by the Phase 0 circular-import fix.

### Phase 0 acceptance checklist

- [x] Cop entry point imports in clean subprocess
- [x] `scripts/run_series.py --help` exits 0
- [x] Startup smoke tests: 5/5 pass
- [x] Baseline failure count documented and classified
- [ ] `uv run pytest --cov=agent --cov-fail-under=85` — deferred to Phase 2 (CI gate)
- [ ] `uv run ruff check .` — deferred to Phase 2
