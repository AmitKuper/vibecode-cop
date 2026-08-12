"""Phase 2 cross-repo conformance tests for CanonicalConfig — minimums and field kinds.

Both cop and thief repositories must pass these tests identically.
"""

from __future__ import annotations

import pytest

from cop_worker.config.canonical_config import CanonicalConfig, ConfigError, FieldKind
from tests.helpers_config_conformance import _VALID_FLAT, _make

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
