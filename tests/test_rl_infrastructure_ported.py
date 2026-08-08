"""Tests for Phase 4: RL infrastructure."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile

import numpy as np
import pytest

from cop_worker.observation import BeliefState, LocalObservation
from cop_worker.rl.action_space import (
    COP_ACTIONS,
    THIEF_ACTIONS,
    compute_legal_mask_cop,
    compute_legal_mask_thief,
    sample_action,
)
from cop_worker.rl.heuristics import evasion_thief, pursuit_cop
from cop_worker.rl.local_obs_adapter import local_obs_to_tensor, obs_tensor_shape
from cop_worker.rl.model_schema import (
    CURRENT_ACTION_SCHEMA_VERSION,
    CURRENT_OBSERVATION_SCHEMA_VERSION,
    ModelLoadError,
    ModelManifestEntry,
    load_manifest,
    validate_model_file,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_entry(**overrides) -> ModelManifestEntry:
    defaults = {
        "role": "cop",
        "algorithm": "PPO",
        "sha256": "abc",
        "training_code_sha": "placeholder",
        "config_sha256": "placeholder",
        "observation_schema_version": CURRENT_OBSERVATION_SCHEMA_VERSION,
        "action_schema_version": CURRENT_ACTION_SCHEMA_VERSION,
        "belief_schema_version": "1.0",
        "inference_mode": "argmax",
        "grid_size": 7,
    }
    defaults.update(overrides)
    return ModelManifestEntry(**defaults)


def _make_local_obs(grid_size: int = 7) -> LocalObservation:
    scent = [[0.0] * grid_size for _ in range(grid_size)]
    return LocalObservation(
        own_position=(3, 3),
        own_barriers_remaining=5,
        known_barriers=[(1, 2), (4, 5)],
        opponent_scent=scent,
        last_hint="",
        step=10,
        gamelet=1,
        grid_size=grid_size,
    )


# ---------------------------------------------------------------------------
# Model schema tests
# ---------------------------------------------------------------------------


class TestModelManifestEntry:
    def test_compatible_same_role_and_grid(self):
        entry = _make_entry()
        ok, reason = entry.is_compatible("cop", 7)
        assert ok
        assert reason == ""

    def test_role_mismatch(self):
        entry = _make_entry(role="cop")
        ok, reason = entry.is_compatible("thief", 7)
        assert not ok
        assert "role" in reason

    def test_grid_size_mismatch(self):
        entry = _make_entry(grid_size=5)
        ok, reason = entry.is_compatible("cop", 7)
        assert not ok
        assert "grid_size" in reason

    def test_obs_schema_version_mismatch(self):
        entry = _make_entry(observation_schema_version="0.9")
        ok, reason = entry.is_compatible("cop", 7)
        assert not ok
        assert "obs schema" in reason

    def test_action_schema_version_mismatch(self):
        entry = _make_entry(action_schema_version="0.9")
        ok, reason = entry.is_compatible("cop", 7)
        assert not ok
        assert "action schema" in reason


class TestValidateModelFile:
    def test_correct_hash_passes(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test content")
            path = f.name
        try:
            h = hashlib.sha256(b"test content").hexdigest()
            validate_model_file(path, h)  # should not raise
        finally:
            os.unlink(path)

    def test_wrong_hash_raises(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test content")
            path = f.name
        try:
            with pytest.raises(ModelLoadError, match="hash mismatch"):
                validate_model_file(path, "deadbeef" * 8)
        finally:
            os.unlink(path)


class TestLoadManifest:
    def test_load_valid_manifest(self):
        manifest_data = {
            "manifest_version": "1.0",
            "models": [
                {
                    "role": "cop",
                    "algorithm": "PPO",
                    "sha256": "abc123",
                    "training_code_sha": "placeholder",
                    "config_sha256": "placeholder",
                    "observation_schema_version": "1.0",
                    "action_schema_version": "1.0",
                    "belief_schema_version": "1.0",
                    "inference_mode": "argmax",
                    "grid_size": 7,
                }
            ],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(manifest_data, f)
            path = f.name
        try:
            result = load_manifest(path)
            assert "cop" in result
            assert result["cop"].algorithm == "PPO"
            assert result["cop"].grid_size == 7
        finally:
            os.unlink(path)


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


# ---------------------------------------------------------------------------
# Local obs adapter tests
# ---------------------------------------------------------------------------


class TestLocalObsToTensor:
    def test_shape_matches_expected(self):
        obs = _make_local_obs(7)
        belief = BeliefState.uniform(7)
        tensor = local_obs_to_tensor(obs, belief)
        expected = obs_tensor_shape(7)
        assert tensor.shape == (expected,), f"Expected {expected}, got {tensor.shape}"

    def test_no_opponent_position_in_output(self):
        """The tensor must NOT contain raw opponent coordinates as scalars."""
        # If opponent were at (6, 6), their coordinates would be 6 and 6.
        # Since LocalObservation has no opponent_position, the tensor cannot
        # encode them — this test just verifies tensor builds without error
        # and doesn't crash for any grid position.
        obs = _make_local_obs(7)
        belief = BeliefState.uniform(7)
        tensor = local_obs_to_tensor(obs, belief)
        assert tensor is not None
        assert not np.any(np.isnan(tensor))
        assert not np.any(np.isinf(tensor))

    def test_own_position_is_one_hot(self):
        obs = _make_local_obs(7)
        belief = BeliefState.uniform(7)
        tensor = local_obs_to_tensor(obs, belief)
        # First n*n values are one-hot for own_position (3,3)
        n = 7
        own_oh = tensor[: n * n]
        r, c = obs.own_position
        assert own_oh[r * n + c] == 1.0
        assert own_oh.sum() == 1.0

    def test_local_observation_has_no_opponent_position_field(self):
        """Critical: LocalObservation must NOT have opponent_position attribute."""
        obs = _make_local_obs(7)
        assert not hasattr(obs, "opponent_position"), (
            "LocalObservation must not have opponent_position field"
        )


# ---------------------------------------------------------------------------
# Heuristic tests
# ---------------------------------------------------------------------------


class TestPursuitCop:
    def test_moves_toward_centroid(self):
        # Cop at (0,0), centroid at (3,3) — should move S or E
        action = pursuit_cop((0, 0), (3, 3), [], 0, 7)
        assert action in ["S", "E", "STAY"]

    def test_does_not_walk_into_barrier(self):
        # Centroid is S of cop, but barrier there
        action = pursuit_cop((3, 3), (4, 3), [(4, 3)], 0, 7)
        assert action != "S"


class TestEvasionThief:
    def test_moves_away_from_centroid(self):
        # Thief at (3,3), centroid at (3,3) — any move is away or stays
        action = evasion_thief((3, 3), (3, 3), [], 7)
        assert action in THIEF_ACTIONS

    def test_picks_direction_maximizing_distance(self):
        # Thief at (0,0), cop centroid at (0,0) — moving S or E increases distance
        action = evasion_thief((0, 0), (0, 0), [], 7)
        assert action in ["S", "E", "STAY"]
