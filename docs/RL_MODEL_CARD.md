# RL Policy Model Card

## Overview
- **Role**: cop (vibecode-cop)
- **Algorithm**: PPO (Proximal Policy Optimization)
- **Status**: PLACEHOLDER — real training required before counted-mode use
- **Schema versions**: observation=1.0, action=1.0, belief=1.0

## Observation Space
Flat feature vector built from `LocalObservation` + `BeliefState`:
- Own position one-hot (grid_size²)
- Barrier grid (grid_size²)
- Opponent scent field (grid_size²)
- Belief heatmap (grid_size²)
- 5 scalar features: barriers_remaining_norm, step_norm, gamelet_norm, entropy_norm, confidence

**No hidden opponent coordinates.** `LocalObservation` deliberately omits `opponent_position`.

## Action Space
- **Cop**: 9 actions — N, S, E, W, STAY, PLACE_N, PLACE_S, PLACE_E, PLACE_W
- **Thief**: 5 actions — N, S, E, W, STAY

## Legal Masking
Actions that would move into barriers or out-of-bounds are masked to -∞ before softmax.
PLACE_* actions are additionally masked when `barriers_remaining == 0`.

## Inference Mode
Default: `argmax` (deterministic). Supports: sample, low_temp, top_k_mix.

## Counted-Mode Requirements
Before this model can be used in counted (competitive) mode:
1. Complete training (≥500k steps)
2. Verify `evaluation_win_rate` in MANIFEST.json
3. Re-compute and update sha256 in MANIFEST.json
4. Schema versions must match CURRENT_*_SCHEMA_VERSION constants

## Limitations
- Placeholder model: random-quality performance
- Not trained on barrier placement strategies
- Single grid_size (7x7) — not portable to other sizes without retraining

## Phase 4 v7 Status

### Heuristic Baseline (ACTIVE in DEVELOPMENT mode)
Belief-driven pursuit/evasion heuristic is active via `AgentOrchestrator.select_move_heuristic()`:
- **Cop**: `pursuit_cop` — greedy Manhattan toward belief centroid (highest-prob cell)
- **Thief**: `evasion_thief` — greedy Manhattan away from belief centroid
- Wired into `peer_turn_loop.py` when `runtime.orchestrator` is set and no RL model loaded

### RL Training: EXTERNAL_PENDING
Real PPO training is required. Current MANIFEST.json has `training_steps=0`.

### Language Policy: NaturalLanguagePolicy
- `NaturalLanguagePolicy` (in `agent/language/deception_policy.py`) with configurable `bluff_probability`
- Intents: TRUTH, LIE, AMBIGUOUS, BLUFF — chosen based on belief entropy
- No numeric coordinates ever appear in hints

### Counted Mode: Rejects Placeholder Model
`_validate_counted_preconditions()` now validates the MANIFEST.json on startup:
- Rejects if `training_steps == 0`
- Rejects if `evaluation_win_rate == 0.0`
- Rejects if role/grid_size incompatible
