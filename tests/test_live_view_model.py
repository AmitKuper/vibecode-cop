"""Tests for the Live GUI view model — role-filtered, no hidden coordinates."""

import dataclasses
import json

import pytest

from cop_worker.gui.live_view_model import LiveViewModel, LiveViewUpdate
from cop_worker.observation import SafeLiveView


def _make_view(**kwargs) -> SafeLiveView:
    defaults = {
        "own_position": (1, 2),
        "belief_heatmap": [[0.02] * 7 for _ in range(7)],
        "opponent_scent": [[0.0] * 7 for _ in range(7)],
        "last_hint": "go north",
        "hint_reliability": 0.75,
        "turn": 3,
        "gamelet": 1,
        "score": {"cop": 0, "thief": 0},
        "own_barriers_remaining": 3,
        "protocol_state": "PLAYING",
        "your_turn": True,
        "connection_healthy": True,
    }
    defaults.update(kwargs)
    return SafeLiveView(**defaults)


class TestLiveViewModelUpdate:
    def test_update_stores_view(self):
        vm = LiveViewModel(role="cop", grid_size=7)
        view = _make_view()
        vm.update(view)
        assert vm.get_current() == view

    def test_get_update_returns_none_before_first_update(self):
        vm = LiveViewModel(role="cop", grid_size=7)
        assert vm.get_update() is None

    def test_event_id_increments(self):
        vm = LiveViewModel(role="cop", grid_size=7)
        vm.update(_make_view(turn=1))
        first = vm.get_update()
        vm.update(_make_view(turn=2))
        second = vm.get_update()
        assert int(second.event_id) > int(first.event_id)

    def test_to_json_contains_view(self):
        vm = LiveViewModel(role="cop", grid_size=7)
        vm.update(_make_view())
        update = vm.get_update()
        data = json.loads(update.to_json())
        assert "view" in data
        assert "event_id" in data
        assert "timestamp_utc" in data

    def test_hidden_coord_rejected_thief(self):
        """_verify_no_hidden_coord raises ValueError when a forbidden key is present."""
        vm = LiveViewModel(role="thief", grid_size=7)
        view = _make_view()
        # Directly test the guard: inject a forbidden key by mocking asdict
        import unittest.mock as mock

        view_dict = dataclasses.asdict(view)
        view_dict["cop_position"] = [1, 2]  # hidden coord leaked

        with (
            mock.patch("cop_worker.gui.live_view_model.asdict", return_value=view_dict),
            pytest.raises(ValueError, match="cop_position"),
        ):
            vm._verify_no_hidden_coord(view)

    def test_view_has_no_opponent_position_field(self):
        """SafeLiveView must not have opponent_position, thief_position, or cop_position fields."""
        field_names = {f.name for f in dataclasses.fields(SafeLiveView)}
        assert "opponent_position" not in field_names
        assert "thief_position" not in field_names
        assert "cop_position" not in field_names

    def test_belief_heatmap_is_2d_list(self):
        view = _make_view()
        assert isinstance(view.belief_heatmap, list)
        assert isinstance(view.belief_heatmap[0], list)
        assert isinstance(view.belief_heatmap[0][0], float)


class TestLiveViewUpdate:
    def test_live_view_update_to_json(self):
        view = _make_view()
        update = LiveViewUpdate(view=view, event_id="5", timestamp_utc="2026-08-04T00:00:00Z")
        data = json.loads(update.to_json())
        assert data["event_id"] == "5"
        assert "view" in data
        assert data["view"]["turn"] == 3
