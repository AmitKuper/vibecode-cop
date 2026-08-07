"""Test that negotiate returns ok with agreed terms."""

from cop_worker.parameter_registry import get_defaults, validate_terms

# Full valid terms: FIXED/MINIMUM params at their minimum allowed values
FULL_VALID_TERMS = {
    "board_size": 7,
    "smell_grid_size": 5,
    "decay_per_step": 0.1,
    "emit_intensity": 0.9,
    "max_steps": 35,
    "survival_threshold": 35,
    "barriers_max": 14,
    "num_games": 6,
    **get_defaults(),
}


def test_negotiate_returns_ok_with_agreed_terms():
    """Full valid terms must pass validate_terms with no errors."""
    errors = validate_terms(FULL_VALID_TERMS)
    assert errors == [], f"Full valid terms must pass, got: {errors}"


def test_negotiate_rejects_invalid_terms():
    """Negotiate with smell_grid_size=3 must return errors."""
    terms = {"smell_grid_size": 3, "board_size": 7, "num_games": 6}
    errors = validate_terms(terms)
    assert any("smell_grid_size" in e for e in errors), (
        f"Expected smell_grid_size error, got: {errors}"
    )
