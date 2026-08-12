"""Tests for Phase 4: RL infrastructure — action space masks and sampling."""

from __future__ import annotations

import numpy as np

from cop_worker.rl.action_space import (
    COP_ACTIONS,
    THIEF_ACTIONS,
    compute_legal_mask_cop,
    compute_legal_mask_thief,
    sample_action,
)

# ---------------------------------------------------------------------------
# Action space tests
# ---------------------------------------------------------------------------


class TestComputeLegalMaskCop:
    def test_all_9_actions_covered(self):
        # Center of grid, no barriers, quota available
        mask = compute_legal_mask_cop((3, 3), [], 5, 7)
        assert len(mask) == 9
        assert len(COP_ACTIONS) == 9

    def test_stay_always_legal_in_open_space(self):
        mask = compute_legal_mask_cop((3, 3), [], 0, 7)
        stay_idx = COP_ACTIONS.index("STAY")
        assert mask[stay_idx]

    def test_place_blocked_when_quota_zero(self):
        mask = compute_legal_mask_cop((3, 3), [], 0, 7)
        for action in ["PLACE_N", "PLACE_S", "PLACE_E", "PLACE_W"]:
            idx = COP_ACTIONS.index(action)
            assert not mask[idx], f"{action} should be blocked when barriers_remaining=0"

    def test_place_allowed_when_quota_positive(self):
        mask = compute_legal_mask_cop((3, 3), [], 3, 7)
        for action in ["PLACE_N", "PLACE_S", "PLACE_E", "PLACE_W"]:
            idx = COP_ACTIONS.index(action)
            assert mask[idx], f"{action} should be allowed when barriers_remaining=3"

    def test_move_blocked_by_barrier(self):
        # Cop at (3,3), barrier at (3,2) = N move blocked
        mask = compute_legal_mask_cop((3, 3), [(3, 2)], 0, 7)
        n_idx = COP_ACTIONS.index("N")
        assert not mask[n_idx]

    def test_move_blocked_by_boundary(self):
        # Cop at (0,0), N and W are out of bounds
        mask = compute_legal_mask_cop((0, 0), [], 0, 7)
        assert not mask[COP_ACTIONS.index("N")]
        assert not mask[COP_ACTIONS.index("W")]

    def test_place_blocked_by_existing_barrier(self):
        # Barrier already at (3,2) — PLACE_N from (3,3) should be blocked
        mask = compute_legal_mask_cop((3, 3), [(3, 2)], 5, 7)
        place_n = COP_ACTIONS.index("PLACE_N")
        assert not mask[place_n]


class TestComputeLegalMaskThief:
    def test_all_5_actions_covered(self):
        mask = compute_legal_mask_thief((3, 3), [], 7)
        assert len(mask) == 5
        assert len(THIEF_ACTIONS) == 5

    def test_stay_legal_open_space(self):
        mask = compute_legal_mask_thief((3, 3), [], 7)
        stay_idx = THIEF_ACTIONS.index("STAY")
        assert mask[stay_idx]

    def test_blocked_by_barrier(self):
        mask = compute_legal_mask_thief((3, 3), [(3, 2)], 7)
        n_idx = THIEF_ACTIONS.index("N")
        assert not mask[n_idx]

    def test_blocked_by_boundary(self):
        mask = compute_legal_mask_thief((0, 0), [], 7)
        assert not mask[THIEF_ACTIONS.index("N")]
        assert not mask[THIEF_ACTIONS.index("W")]


class TestSampleAction:
    def test_argmax_picks_highest_logit(self):
        logits = np.array([1.0, 5.0, 2.0, 3.0, 4.0])
        mask = np.array([True, True, True, True, True])
        result = sample_action(logits, mask, mode="argmax")
        assert result == 1  # index of 5.0

    def test_argmax_respects_mask(self):
        logits = np.array([1.0, 5.0, 2.0, 3.0, 4.0])
        mask = np.array([True, False, True, True, True])  # index 1 masked out
        result = sample_action(logits, mask, mode="argmax")
        assert result == 4  # next highest legal: 4.0 at index 4

    def test_sample_returns_legal_action(self):
        logits = np.ones(5)
        mask = np.array([True, False, True, False, True])
        for _ in range(20):
            result = sample_action(logits, mask, mode="sample")
            assert mask[result], f"Sampled illegal action {result}"
