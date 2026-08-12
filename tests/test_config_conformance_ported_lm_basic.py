"""Phase 2 cross-repo conformance tests for CanonicalConfig — construction and field violations.

Both cop and thief repositories must pass these tests identically.
"""

from __future__ import annotations

import pytest

from cop_worker.config.canonical_config import CanonicalConfig, ConfigError
from tests.helpers_config_conformance import _VALID_FLAT, _drop, _make

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
