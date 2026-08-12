"""Phase 2 cross-repo conformance tests for CanonicalConfig — scent lock and shared factory.

Both cop and thief repositories must pass these tests identically.
"""

from __future__ import annotations

import pytest

from cop_worker.config.canonical_config import CanonicalConfig
from tests.helpers_config_conformance import _VALID_FLAT

# ---------------------------------------------------------------------------
# 6. Scent model lock (numerical golden vector)
# ---------------------------------------------------------------------------


class TestScentModelLock:
    """Verify that the scent model constants are locked at Appendix-F values."""

    def test_scent_center_golden_value(self):
        cfg = CanonicalConfig.from_dict(_VALID_FLAT)
        assert cfg.scent_center == pytest.approx(0.9, abs=1e-9)

    def test_scent_decay_golden_value(self):
        cfg = CanonicalConfig.from_dict(_VALID_FLAT)
        assert cfg.scent_decay == pytest.approx(0.10, abs=1e-9)

    def test_scent_field_size_golden_value(self):
        cfg = CanonicalConfig.from_dict(_VALID_FLAT)
        assert cfg.scent_field_size == 5

    def test_scent_sha256_golden_vector(self):
        """Exact SHA-256 must match between both repos for same input."""
        import hashlib
        import json

        cfg = CanonicalConfig.from_dict(_VALID_FLAT)
        # Re-compute independently and compare
        fields = {
            "capture_cop": 20,
            "capture_thief": 5,
            "diversity_reward": 10,
            "grid_size": 7,
            "max_barriers": 14,
            "max_counted_games": 10,
            "max_turns": 35,
            "min_games_to_pass": 2,
            "num_gamelets": 6,
            "scent_center": 0.9,
            "scent_decay": 0.1,
            "scent_field_size": 5,
            "survival_cop": 5,
            "survival_threshold": 35,
            "survival_thief": 10,
        }
        expected_sha = hashlib.sha256(
            json.dumps(fields, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
                "utf-8"
            )
        ).hexdigest()
        assert cfg.config_sha256 == expected_sha


# ---------------------------------------------------------------------------
# 7. from_shared_config factory
# ---------------------------------------------------------------------------


class TestFromSharedConfig:
    _SHARED = {
        "board_and_agents": {"grid_size": 7},
        "movement_and_barriers": {
            "max_barriers": 14,
            "max_moves": 35,
            "survival_threshold": 35,
        },
        "scoring": {
            "capture_cop": 20,
            "capture_thief": 5,
            "survival_cop": 5,
            "survival_thief": 10,
        },
        "pheromones": {
            "pheromone_center_intensity": 0.9,
            "pheromone_decay": 0.10,
            "pheromone_grid_size": 5,
        },
        "network_and_league": {
            "num_gamelets": 6,
            "min_games_to_pass": 2,
            "max_games_per_team": 10,
            "diversity_reward": 10,
        },
    }

    def test_from_shared_config_succeeds(self):
        cfg = CanonicalConfig.from_shared_config(self._SHARED)
        assert cfg.grid_size == 7
        assert cfg.num_gamelets == 6
        assert cfg.scent_center == pytest.approx(0.9)

    def test_from_shared_config_sha256_matches_from_dict(self):
        cfg_shared = CanonicalConfig.from_shared_config(self._SHARED)
        cfg_flat = CanonicalConfig.from_dict(_VALID_FLAT)
        assert cfg_shared.config_sha256 == cfg_flat.config_sha256
