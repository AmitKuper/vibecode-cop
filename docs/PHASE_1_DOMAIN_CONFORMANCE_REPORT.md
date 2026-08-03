# Phase 1 Domain Conformance Report — vibecode-cop

**Date:** 2026-08-03  
**Starting SHA:** `3beeca4` (Phase 0 commit)

## Summary

Phase 1 created a deterministic shared domain core (`agent/domain/`) with pure typed schemas and a single canonical transition function. Cross-repository conformance is enforced by a shared fixture vector set.

---

## 1.1 Pure Domain Transition API

**New file:** `agent/domain/transition.py`

`apply_joint_action(state, cop_action, thief_action, config) → TransitionResult` handles:
- PLACE_* barrier actions (cop only)
- Barrier-on-thief capture (immediate COP_WIN before movement)
- Orthogonal movement with bounds/barrier validation
- Illegal moves → STAY fallback (cop_action_legal/thief_action_legal flags)
- Short aliases (N/S/E/W accepted)
- Position-overlap capture
- Survival threshold (turn >= max_turns → THIEF_WIN)
- Trapped-thief detection (STAY excluded from escape)
- Scent field update (Appendix-F 5×5 kernel, 0.9 decay)
- Immutable `TransitionResult` dataclass (frozen)

---

## 1.2 Strict Typed Schemas

**New file:** `agent/domain/types.py`

| Schema | Purpose |
|--------|---------|
| `DomainState` | Full game state with position bounds validation |
| `PrivateState` | Local-only nonces — never serialized to opponent |
| `LocalObservation` | What strategy/LLM receives (own position + opponent scent) |
| `BeliefState` | Normalized probability distribution over opponent location |
| `CommitmentRecord` | Opponent commitment storage |
| `RevealRecord` | Opponent reveal — nonce deliberately absent |
| `AuditSummary` | Per-game audit result |
| `GameletResult` | Gamelet score record |
| `ResultAgreement` | Series result (produced only after bilateral agreement) |

---

## 1.3 Configuration-Driven Validation

**New file:** `agent/domain/config_validator.py`

`validate_game_config(path) → GameConfig` loads `config/game.json` and enforces
all Appendix-F fixed/minimum values:

| Constraint | Value | Enforcement |
|------------|-------|-------------|
| grid_size | == 7 | Pydantic validator |
| num_agents | == 2 | Pydantic validator |
| max_barriers | == 14 | Pydantic validator |
| max_moves | >= 35 | Pydantic validator |
| num_gamelets | == 6 | Pydantic validator |
| diversity_reward | == 10 | Pydantic validator |
| min_games_to_pass | >= 2 | Pydantic validator |
| max_games_per_team | <= 10 | Pydantic validator |
| capture_cop score | == 20 | Pydantic validator |
| survival_thief score | == 10 | Pydantic validator |

---

## 1.4 Cross-Repository Conformance

**New files:**
- `tests/fixtures/transcript_vectors.json` (10 vectors, byte-identical in both repos)
- `tests/test_domain_conformance.py` (26 tests)

**Vectors cover:**
- Normal movement (both legal moves)
- Position-overlap capture
- Barrier placement on empty cell
- Barrier-on-thief capture (immediate COP_WIN)
- Trapped thief (no orthogonal escape)
- Survival at max_turns (THIEF_WIN)
- Illegal cop move (out of bounds → STAY)
- Illegal thief move (into barrier → STAY)
- Corner thief with one exit (not trapped)
- Short alias moves (N → NORTH, S → SOUTH)

---

## Board.from_dict() Strict Validation

`Board.from_dict()` now raises `ValueError` when `cop_position` or `thief_position`
is missing. Silent defaults were removed because they allowed a role-filtered
observation to reconstruct private opponent state.

**Stale test updated:** `test_from_dict_defaults` → `test_from_dict_requires_both_positions`

**RL path fix:** `build_observation()` in `orchestrator_crew_helpers.py` now includes
full board state (both positions) in `grid_state` for RL policy inference. The
role-filtered `role_state` (own position only) remains in the observation dict for LLM/crew.

---

## Architecture Decision

See `docs/ADR_001_shared_code_model.md` — chose identically vendored `agent/domain/`
over a versioned common package. Cross-repo identity enforced by conformance test suite.

---

## Quality Gate Results

| Gate | Result |
|------|--------|
| pytest | 661 passed, 0 failed |
| ruff check | All checks passed |
| ruff format | 175 files formatted |
