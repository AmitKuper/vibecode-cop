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

#### Failure classification (Phase 0 baseline)

| Category | Count | Example |
|----------|-------|---------|
| Stale scent-decay expectation (additive accumulates > 0.9) | 1 | `test_compliance.py` |
| RL model channel mismatch (5-channel obs vs 4-channel checkpoint) | ~5 | `RuntimeError: mat1 and mat2 shapes cannot be multiplied` |
| `fastapi` not installed (webserver/live-view tests) | ~5 | `ModuleNotFoundError: No module named 'fastapi'` |
| Stale game-rule test (barrier-on-thief now triggers COP_WIN earlier) | ~2 | `assert <GameOutcome.COP_WIN> == <GameOutcome.ONGOING>` |
| Stale crewAI/LLM behavior expectation | ~8 | Various |
| Missing `opponent_commitments.json` in empty-audit test | 1 | `assert False is True` |
| `test_rl_tools_reports.py` CrewAI factory tests | 18 | Missing CrewAI factory implementations |
| Other pre-existing environment/external | ~18 | Various |

None of the 58 failures were introduced by the Phase 0 circular-import fix.

### Phase 0 acceptance checklist

- [x] Cop entry point imports in clean subprocess
- [x] `scripts/run_series.py --help` exits 0
- [x] Startup smoke tests: 5/5 pass
- [x] Baseline failure count documented and classified

---

## Phase 0.5 — Reproducible Green Quality Baseline (2026-08-03)

### Environment

| Item | Value |
|------|-------|
| Python | 3.13.14 |
| Platform | Windows 11 Pro 10.0.26200 |
| uv | 0.11.33 |
| pytest | 9.1.1 |
| pytest-cov | 5.x |
| coverage | 7.x |
| ruff | 0.9.x |
| Baseline SHA | a38c930a209e129ee2873e5eed4b686a033a6620 |
| Tested SHA | (this commit) |
| Timestamp | 2026-08-03 |

### Full test suite result

Command: `uv run python -m pytest tests/ agent/tests/ -q --tb=short`

Result: **607 passed, 1 skipped, 0 failed, 33 warnings** in ~87s

The 1 skipped test is the RL policy load test — skipped because no trained model files
are present in this checkout. The skip uses `pytest.importorskip` or file-existence guard
so it does not pollute CI. Documented in `docs/KNOWN_DEVIATIONS.md` (DEV-001).

### Coverage result

Command: `uv run python -m pytest tests/ agent/tests/ --cov=agent --cov-branch --cov-report=term-missing --cov-report=xml --cov-fail-under=85 -q`

Result: **87.71% total branch coverage** (target: ≥85%) ✓

Key module coverage:
- `agent/board.py`: 96%
- `agent/rules_engine.py`: 93%
- `agent/rules_outcomes.py`: 90%
- `agent/peer_audit.py`: 94%
- `agent/peer_turn_helpers.py`: 94%
- `agent/rl/environment.py`: 93%
- `agent/rl/observation.py`: 95%
- `agent/rl/policy.py`: 95%
- `agent/rl/policy_loader.py`: 91%

Coverage XML: `coverage.xml`

### Ruff result

Commands:
- `uv run ruff check .` → **All checks passed!**
- `uv run ruff format --check .` → **167 files already formatted**

### JUnit XML

File: `results/test-results.xml`

### Phase 0.5 acceptance checklist

- [x] `uv run python -m pytest tests/ agent/tests/ -q` — 607 passed, 0 failed
- [x] `uv run python -m pytest tests/ agent/tests/ --cov=agent --cov-fail-under=85` — 87.71%
- [x] `uv run ruff check .` — All checks passed
- [x] `uv run ruff format --check .` — All files formatted
- [x] `results/test-results.xml` generated
- [x] `coverage.xml` generated
- [x] `docs/KNOWN_DEVIATIONS.md` created
- [x] `docs/PHASE_0_5_REPORT.md` created
