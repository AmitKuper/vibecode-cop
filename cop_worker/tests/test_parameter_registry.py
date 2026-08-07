"""Tests for cop_worker.parameter_registry — validate_terms and PARAMETER_REGISTRY."""

from cop_worker.parameter_registry import PARAMETER_REGISTRY, validate_terms

VALID_TERMS = {
    "board_size": 7,
    "smell_grid_size": 5,
    "decay_per_step": 0.1,
    "emit_intensity": 0.9,
    "max_steps": 35,
    "survival_threshold": 35,
    "barriers_max": 14,
    "num_games": 6,
    "setting": "Haifa",
    "hint_max_words": 15,
    "axis_origin_corner": "top-left",
    "axis_start_index": 0,
    "thief_start": [3, 3],
    "cop_start": [0, 0],
}


def test_fixed_param_exact_value_passes():
    """FIXED parameter at exact required value produces no violations."""
    violations = validate_terms(VALID_TERMS)
    assert violations == []


def test_fixed_param_wrong_value_fails():
    """FIXED parameter with wrong value produces a violation."""
    bad = {**VALID_TERMS, "smell_grid_size": 3}
    violations = validate_terms(bad)
    assert any("smell_grid_size" in v for v in violations)


def test_minimum_param_at_minimum_passes():
    """MINIMUM parameter at exactly the minimum value passes."""
    at_min = {**VALID_TERMS, "board_size": 7}
    assert validate_terms(at_min) == []


def test_minimum_param_above_minimum_passes():
    """MINIMUM parameter above the minimum value passes."""
    above = {**VALID_TERMS, "board_size": 10}
    assert validate_terms(above) == []


def test_minimum_param_below_minimum_fails():
    """MINIMUM parameter below required value produces a violation."""
    bad = {**VALID_TERMS, "board_size": 5}
    violations = validate_terms(bad)
    assert any("board_size" in v for v in violations)


def test_negotiated_param_any_value_passes():
    """NEGOTIATED parameter with any value does not produce a violation."""
    custom = {**VALID_TERMS, "setting": "Tel Aviv", "hint_max_words": 20}
    assert validate_terms(custom) == []


def test_missing_required_param_fails():
    """Missing FIXED or MINIMUM parameter produces a violation."""
    missing = {k: v for k, v in VALID_TERMS.items() if k != "board_size"}
    violations = validate_terms(missing)
    assert any("board_size" in v for v in violations)


def test_registry_has_expected_terms():
    """PARAMETER_REGISTRY contains all mandatory terms."""
    names = {s.name for s in PARAMETER_REGISTRY}
    mandatory = {
        "board_size",
        "smell_grid_size",
        "max_steps",
        "survival_threshold",
        "barriers_max",
        "num_games",
        "decay_per_step",
        "emit_intensity",
    }
    assert mandatory.issubset(names)


def test_survival_threshold_minimum_35():
    """survival_threshold must be >= 35 per spec."""
    bad = {**VALID_TERMS, "survival_threshold": 10}
    violations = validate_terms(bad)
    assert any("survival_threshold" in v for v in violations)


def test_num_games_fixed_6():
    """num_games is FIXED at 6."""
    bad = {**VALID_TERMS, "num_games": 4}
    violations = validate_terms(bad)
    assert any("num_games" in v for v in violations)
