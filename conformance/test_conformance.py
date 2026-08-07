"""Conformance vector tests — verifies protocol compliance against golden vectors."""

import json
from pathlib import Path

import pytest


def load_vector(filename: str) -> dict:
    """Load a conformance vector JSON file."""
    path = Path(__file__).parent / "vectors" / filename
    return json.loads(path.read_text())


@pytest.mark.parametrize("case", load_vector("scent_model.json")["cases"])
def test_scent_model_output(case):
    """Scent model output must match golden vector."""
    pytest.importorskip("cop_worker.scent")
    from cop_worker.scent import compute_scent_grid

    result = compute_scent_grid(
        cop_position=tuple(case["cop_position"]),
        board_size=case["board_size"],
        grid_size=case["grid_size"],
        emit_intensity=case["emit_intensity"],
        decay_per_step=case["decay_per_step"],
    )
    import numpy as np

    expected = np.array(case["expected_output"], dtype=float)
    actual = np.array(result, dtype=float)
    assert actual.shape == expected.shape, f"Shape mismatch for {case['id']}"
    np.testing.assert_allclose(
        actual,
        expected,
        rtol=1e-5,
        atol=1e-6,
        err_msg=f"Scent mismatch for case {case['id']}",
    )


@pytest.mark.parametrize("case", load_vector("commit_construction.json")["cases"])
def test_commit_construction(case):
    """SHA256 commitment must match golden vector."""
    if case["expected_hash"] == "PLACEHOLDER_COMPUTE_AT_RUNTIME":
        pytest.skip("placeholder hash not yet computed")
    pytest.importorskip("cop_worker.crypto")
    from cop_worker.crypto import build_commitment

    result = build_commitment(nonce=case["nonce"], action=case["action"])
    assert result == case["expected_hash"], f"Commitment mismatch for {case['id']}"


@pytest.mark.parametrize("case", load_vector("config_validation.json")["cases"])
def test_config_validation(case):
    """Parameter validation must pass/fail per registry rules."""
    pytest.importorskip("cop_worker.parameter_registry")
    from cop_worker.parameter_registry import validate_terms

    violations = validate_terms(case["proposed_terms"])
    if case["expected_valid"]:
        assert violations == [], f"Expected valid, got violations: {violations}"
    else:
        assert len(violations) > 0, f"Expected violations for {case['id']}, got none"
        if "expected_violation_contains" in case:
            key = case["expected_violation_contains"]
            assert any(key in v for v in violations), (
                f"Expected violation containing '{key}', got: {violations}"
            )
