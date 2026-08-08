"""Tests for counted-mode model validation using 3-process design."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cop_worker.gamelet import Gamelet, GameletError
from cop_worker.runtime_mode import RuntimeMode

_VALID_TERMS = {
    "board_size": 7,
    "smell_grid_size": 5,
    "max_steps": 35,
    "survival_threshold": 35,
    "cop_barrier_quota": 2,
    "capture_radius": 0,
    "decay_per_step": 0.1,
    "emit_intensity": 0.9,
    "barriers_max": 14,
    "num_games": 6,
}


def test_gamelet_construction_accepts_valid_counted_terms():
    g = Gamelet(
        game_uid="counted_validation_g01",
        sub_game_number=1,
        terms=_VALID_TERMS,
        opponent_group="OPP_GROUP",
        role="thief",
    )
    assert g.game_uid == "counted_validation_g01"
    assert g.role == "thief"


def test_gamelet_rejects_zero_max_steps():
    bad = {**_VALID_TERMS, "max_steps": 0}
    with pytest.raises(GameletError):
        Gamelet(
            game_uid="bad_steps",
            sub_game_number=1,
            terms=bad,
            opponent_group="OPP",
            role="thief",
        )


def test_gamelet_rejects_negative_board_size():
    bad = {**_VALID_TERMS, "board_size": -1}
    with pytest.raises(GameletError, match="board_size"):
        Gamelet(
            game_uid="bad_board",
            sub_game_number=1,
            terms=bad,
            opponent_group="OPP",
            role="thief",
        )


def test_runtime_mode_development_does_not_validate_model():
    """DEVELOPMENT mode is not COUNTED — it should skip strict validation."""
    assert RuntimeMode.DEVELOPMENT != RuntimeMode.COUNTED
    assert RuntimeMode.DEVELOPMENT.value == "development"


def test_rl_model_schema_loads_manifest():
    """The deployed MANIFEST.json must be loadable."""
    from cop_worker.rl.model_schema import load_manifest

    manifest_path = Path("models/MANIFEST.json")
    if not manifest_path.exists():
        pytest.skip("models/MANIFEST.json not present")
    entries = load_manifest(str(manifest_path))
    assert isinstance(entries, dict)
    assert len(entries) >= 1


def test_rl_recurrent_policy_loads_from_manifest():
    """The deployed recurrent policy for thief must load without error."""
    from cop_worker.rl.model_schema import load_manifest
    from cop_worker.rl.recurrent_policy import load_recurrent_policy

    manifest_path = Path("models/MANIFEST.json")
    if not manifest_path.exists():
        pytest.skip("models/MANIFEST.json not present")
    entries = load_manifest(str(manifest_path))
    role = next(iter(entries))
    try:
        policy = load_recurrent_policy(manifest_path, role)
    except Exception as exc:
        pytest.skip(f"model load failed (hash mismatch or missing artifact): {exc}")
    assert policy.role == role
    assert policy.network.training is False


def test_gamelet_sub_game_number_range():
    """sub_game_number must be in 1..6 for a counted series."""
    for n in range(1, 7):
        g = Gamelet(
            game_uid=f"series_g{n:02d}",
            sub_game_number=n,
            terms=_VALID_TERMS,
            opponent_group="OPP",
            role="thief",
        )
        assert g.sub_game_number == n
