"""Tests for ReplayViewer — step-by-step navigation of gamelet logs."""

import json
from pathlib import Path

from cop_worker.replay.viewer import ReplayViewer


def make_log(tmp_path: Path, steps=3) -> Path:
    """Write a minimal gamelet log JSON to a temp file."""
    log = {
        "game_uid": "rv_test_001",
        "sub_game_number": 1,
        "role": "police",
        "steps": [{"step": i + 1, "action": "move"} for i in range(steps)],
    }
    p = tmp_path / "gamelet.json"
    p.write_text(json.dumps(log))
    return p


def test_viewer_starts_at_start(tmp_path):
    """Viewer must start at the first step."""
    viewer = ReplayViewer(make_log(tmp_path))
    assert viewer.is_at_start() is True


def test_viewer_step_forward_advances(tmp_path):
    """step_forward must return a step record."""
    viewer = ReplayViewer(make_log(tmp_path, steps=3))
    step = viewer.step_forward()
    assert step is not None


def test_viewer_is_at_end_after_all_steps(tmp_path):
    """After advancing past all steps, is_at_end must be True."""
    viewer = ReplayViewer(make_log(tmp_path, steps=2))
    viewer.step_forward()
    assert viewer.is_at_end() is True


def test_viewer_step_forward_at_end_returns_none(tmp_path):
    """step_forward at the last step must return None."""
    viewer = ReplayViewer(make_log(tmp_path, steps=1))
    result = viewer.step_forward()
    assert result is None


def test_current_state_returns_game_uid(tmp_path):
    """current_state must include game_uid from the log."""
    viewer = ReplayViewer(make_log(tmp_path))
    state = viewer.current_state()
    assert state["game_uid"] == "rv_test_001"
