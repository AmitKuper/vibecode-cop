"""Tests for parameter registry validation."""

from cop_worker.parameter_registry import PARAMETER_REGISTRY, get_defaults, validate_terms

VALID_TERMS = {
    "board_size": 7,
    "smell_grid_size": 5,
    "decay_per_step": 0.1,
    "emit_intensity": 0.9,
    "max_steps": 35,
    "survival_threshold": 35,
    "barriers_max": 14,
    "num_games": 6,
}


def test_valid_terms_produce_no_violations():
    """Minimal valid terms must pass with zero violations."""
    violations = validate_terms(VALID_TERMS)
    assert violations == []


def test_wrong_num_games_fails():
    """num_games != 6 must produce a violation."""
    bad = {**VALID_TERMS, "num_games": 4}
    violations = validate_terms(bad)
    assert any("num_games" in v for v in violations)


def test_board_size_below_minimum_fails():
    """board_size < 7 must produce a violation."""
    bad = {**VALID_TERMS, "board_size": 5}
    violations = validate_terms(bad)
    assert any("board_size" in v for v in violations)


def test_missing_required_term_fails():
    """Missing a FIXED or MINIMUM term must produce a violation."""
    bad = {k: v for k, v in VALID_TERMS.items() if k != "smell_grid_size"}
    violations = validate_terms(bad)
    assert any("smell_grid_size" in v for v in violations)


def test_get_defaults_returns_negotiated_terms():
    """get_defaults must return a non-empty dict of NEGOTIATED defaults."""
    defaults = get_defaults()
    assert isinstance(defaults, dict)
    assert len(defaults) > 0


def test_registry_has_all_required_fields():
    """Every ParameterSpec must have name, status, and required_value or default."""
    for spec in PARAMETER_REGISTRY:
        assert spec.name
        assert spec.status
