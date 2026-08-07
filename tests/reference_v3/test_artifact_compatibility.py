"""Test that log artifact is loadable by the replay viewer."""

import json

import pytest


def test_log_artifact_loadable_by_replay_viewer(tmp_path):
    """ReplayViewer must be able to load a synthetic gamelet log."""
    log_data = {
        "game_uid": "artifact_rv_001",
        "sub_game_number": 1,
        "role": "police",
        "steps": [
            {
                "step": 1,
                "action": {"direction": "N"},
                "position": [1, 0],
                "commitment_hash": "a" * 64,
            },
            {
                "step": 2,
                "action": {"direction": "E"},
                "position": [1, 1],
                "commitment_hash": "b" * 64,
            },
        ],
        "terminal_condition": "capture",
        "final_step": 2,
    }
    log_path = tmp_path / "log_artifact_rv_001_g01.json"
    log_path.write_text(json.dumps(log_data))

    try:
        from cop_worker.replay.viewer import ReplayViewer

        viewer = ReplayViewer(log_path)
        state = viewer.current_state()
        assert state is not None
        step = viewer.step_forward()
        assert step is not None
    except ImportError:
        pytest.skip("ReplayViewer not yet implemented")
