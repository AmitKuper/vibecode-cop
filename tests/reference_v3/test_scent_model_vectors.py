"""Test scent model output matches conformance vectors."""

import json
from pathlib import Path

import pytest


def load_vector(filename):
    """Load a conformance vector JSON file."""
    path = Path(__file__).parent.parent.parent / "conformance" / "vectors" / filename
    return json.loads(path.read_text())


@pytest.mark.parametrize("case", load_vector("scent_model.json")["cases"])
def test_scent_output_matches_pinned_vectors(case):
    """Scent model output must match golden vectors exactly."""
    try:
        from cop_worker.scent import compute_scent_grid

        result = compute_scent_grid(
            cop_position=case["cop_position"],
            board_size=case["board_size"],
            grid_size=case["grid_size"],
            emit_intensity=case["emit_intensity"],
            decay_per_step=case["decay_per_step"],
        )
        expected = case["expected_output"]
        assert len(result) == len(expected), "grid row count mismatch"
        for row_idx, (res_row, exp_row) in enumerate(zip(result, expected, strict=True)):
            assert res_row == pytest.approx(exp_row, abs=1e-4), f"row {row_idx} mismatch"
    except ImportError:
        pytest.skip("compute_scent_grid not yet implemented")
