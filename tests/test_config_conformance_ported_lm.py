"""Phase 2 cross-repo conformance tests for CanonicalConfig and related machinery.

Both cop and thief repositories must pass these tests identically.
"""

from __future__ import annotations

import pytest

from cop_worker.config.canonical_config import CanonicalConfig, ConfigError, FieldKind

# ---------------------------------------------------------------------------
# Minimal valid flat config (all Appendix-F fields, all constraints met)
# ---------------------------------------------------------------------------
_VALID_FLAT = {
    "grid_size": 7,
    "max_barriers": 14,
    "max_turns": 35,
    "survival_threshold": 35,
    "num_gamelets": 6,
    "min_games_to_pass": 2,
    "max_counted_games": 10,
    "diversity_reward": 10,
    "capture_cop": 20,
    "capture_thief": 5,
    "survival_cop": 5,
    "survival_thief": 10,
    "scent_center": 0.9,
    "scent_decay": 0.10,
    "scent_field_size": 5,
}


def _make(**overrides) -> dict:
    d = dict(_VALID_FLAT)
    d.update(overrides)
    return d


def _drop(field: str) -> dict:
    d = dict(_VALID_FLAT)
    del d[field]
    return d


# ---------------------------------------------------------------------------
# 1. Basic construction
# ---------------------------------------------------------------------------


class TestCanonicalConfigBasic:
    def test_valid_flat_config_accepted(self):
        cfg = CanonicalConfig.from_dict(_VALID_FLAT)
        assert cfg.grid_size == 7
        assert cfg.num_gamelets == 6

    def test_config_sha256_is_64_hex_chars(self):
        cfg = CanonicalConfig.from_dict(_VALID_FLAT)
        sha = cfg.config_sha256
        assert len(sha) == 64
        assert all(c in "0123456789abcdef" for c in sha)

    def test_identical_inputs_produce_identical_sha256(self):
        cfg1 = CanonicalConfig.from_dict(_VALID_FLAT)
        cfg2 = CanonicalConfig.from_dict(_VALID_FLAT)
        assert cfg1.config_sha256 == cfg2.config_sha256

    def test_different_inputs_produce_different_sha256(self):
        cfg1 = CanonicalConfig.from_dict(_make(grid_size=7))
        cfg2 = CanonicalConfig.from_dict(_make(grid_size=8))
        assert cfg1.config_sha256 != cfg2.config_sha256

    def test_to_dict_round_trips(self):
        cfg = CanonicalConfig.from_dict(_VALID_FLAT)
        d = cfg.to_dict()
        assert d["grid_size"] == 7
        assert d["num_gamelets"] == 6


# ---------------------------------------------------------------------------
# 2. Missing mandatory fields
# ---------------------------------------------------------------------------


class TestMissingFields:
    @pytest.mark.parametrize(
        "field",
        [
            "grid_size",
            "max_barriers",
            "max_turns",
            "num_gamelets",
            "capture_cop",
            "scent_center",
        ],
    )
    def test_missing_field_raises_config_error(self, field):
        with pytest.raises(ConfigError, match="Missing mandatory fields"):
            CanonicalConfig.from_dict(_drop(field))


# ---------------------------------------------------------------------------
# 3. FIXED field violations
# ---------------------------------------------------------------------------


class TestFixedFieldViolations:
    @pytest.mark.parametrize(
        "field,bad_value",
        [
            ("num_gamelets", 5),
            ("num_gamelets", 7),
            ("min_games_to_pass", 3),
            ("max_counted_games", 9),
            ("diversity_reward", 5),
            ("capture_cop", 10),
            ("capture_thief", 10),
            ("survival_cop", 10),
            ("survival_thief", 5),
            ("scent_center", 0.5),
            ("scent_decay", 0.05),
            ("scent_field_size", 7),
        ],
    )
    def test_fixed_field_wrong_value_raises(self, field, bad_value):
        with pytest.raises(ConfigError, match="FIXED field"):
            CanonicalConfig.from_dict(_make(**{field: bad_value}))

    def test_num_gamelets_must_be_exactly_6(self):
        with pytest.raises(ConfigError):
            CanonicalConfig.from_dict(_make(num_gamelets=4))

    def test_capture_cop_must_be_20(self):
        with pytest.raises(ConfigError):
            CanonicalConfig.from_dict(_make(capture_cop=15))


# ---------------------------------------------------------------------------
# 4. MINIMUM field semantics
# ---------------------------------------------------------------------------


class TestMinimumFields:
    def test_grid_size_at_minimum_accepted(self):
        cfg = CanonicalConfig.from_dict(_make(grid_size=7))
        assert cfg.grid_size == 7

    def test_grid_size_above_minimum_accepted(self):
        cfg = CanonicalConfig.from_dict(_make(grid_size=9))
        assert cfg.grid_size == 9

    def test_grid_size_below_minimum_raises(self):
        with pytest.raises(ConfigError, match="MINIMUM field"):
            CanonicalConfig.from_dict(_make(grid_size=5))

    def test_max_barriers_at_minimum_accepted(self):
        cfg = CanonicalConfig.from_dict(_make(max_barriers=14))
        assert cfg.max_barriers == 14

    def test_max_barriers_above_minimum_accepted(self):
        cfg = CanonicalConfig.from_dict(_make(max_barriers=20))
        assert cfg.max_barriers == 20

    def test_max_barriers_below_minimum_raises(self):
        with pytest.raises(ConfigError, match="MINIMUM field"):
            CanonicalConfig.from_dict(_make(max_barriers=10))

    def test_max_turns_at_minimum_accepted(self):
        cfg = CanonicalConfig.from_dict(_make(max_turns=35))
        assert cfg.max_turns == 35

    def test_max_turns_above_minimum_accepted(self):
        cfg = CanonicalConfig.from_dict(_make(max_turns=50))
        assert cfg.max_turns == 50

    def test_max_turns_below_minimum_raises(self):
        with pytest.raises(ConfigError, match="MINIMUM field"):
            CanonicalConfig.from_dict(_make(max_turns=20))

    def test_survival_threshold_below_minimum_raises(self):
        with pytest.raises(ConfigError, match="MINIMUM field"):
            CanonicalConfig.from_dict(_make(survival_threshold=30))


# ---------------------------------------------------------------------------
# 5. Field kind metadata
# ---------------------------------------------------------------------------


class TestFieldKindMetadata:
    def test_grid_size_is_minimum(self):
        cfg = CanonicalConfig.from_dict(_VALID_FLAT)
        assert cfg.kind("grid_size") == FieldKind.MINIMUM

    def test_max_barriers_is_minimum(self):
        cfg = CanonicalConfig.from_dict(_VALID_FLAT)
        assert cfg.kind("max_barriers") == FieldKind.MINIMUM

    def test_num_gamelets_is_fixed(self):
        cfg = CanonicalConfig.from_dict(_VALID_FLAT)
        assert cfg.kind("num_gamelets") == FieldKind.FIXED

    def test_capture_cop_is_fixed(self):
        cfg = CanonicalConfig.from_dict(_VALID_FLAT)
        assert cfg.kind("capture_cop") == FieldKind.FIXED

    def test_scent_center_is_fixed(self):
        cfg = CanonicalConfig.from_dict(_VALID_FLAT)
        assert cfg.kind("scent_center") == FieldKind.FIXED

    def test_unknown_field_raises_key_error(self):
        cfg = CanonicalConfig.from_dict(_VALID_FLAT)
        with pytest.raises(KeyError):
            cfg.kind("nonexistent_field")


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
