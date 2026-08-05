"""Live-view and replay HTTP route contracts, including unavailable states."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

import agent.gui.app as gui
import agent.replay.app as replay
from agent.gui.live_view_model import LiveViewModel
from agent.observation import SafeLiveView
from agent.replay.replay_app import ReplayState


def _safe_view() -> SafeLiveView:
    return SafeLiveView(
        own_position=(1, 2),
        belief_heatmap=[[1.0]],
        opponent_scent=[[0.5]],
        last_hint="safe",
        hint_reliability=0.8,
        turn=3,
        gamelet=2,
        score={"cop": 10, "thief": 5},
        own_barriers_remaining=1,
        protocol_state="COMMIT",
        your_turn=True,
        connection_healthy=True,
    )


@pytest.mark.asyncio
async def test_gui_index_and_current_view_states(monkeypatch) -> None:
    monkeypatch.setattr(gui, "_view_model", None)
    index = await gui.index()
    assert "Local Truth Live View" in index.body.decode()
    unavailable = await gui.current_view()
    assert unavailable.status_code == 503
    assert json.loads(unavailable.body)["error"] == "no game active"

    vm = LiveViewModel("cop", 7)
    gui.set_view_model(vm)
    empty = await gui.current_view()
    assert empty.status_code == 503
    vm.update(_safe_view())
    current = await gui.current_view()
    payload = json.loads(current.body)
    assert payload["view"]["own_position"] == [1, 2]
    assert "opponent_position" not in current.body.decode()


class _Request:
    def __init__(self, values):
        self.values = iter(values)

    async def is_disconnected(self):
        return next(self.values)


@pytest.mark.asyncio
async def test_gui_stream_yields_update_and_stops_on_disconnect(monkeypatch) -> None:
    vm = LiveViewModel("cop", 7)
    vm.update(_safe_view())
    monkeypatch.setattr(gui, "_view_model", vm)
    response = await gui.stream(_Request([False, True]))
    event = await anext(response.body_iterator)
    assert event.startswith("data: ")
    await response.body_iterator.aclose()

    disconnected = await gui.stream(_Request([True]))
    with pytest.raises(StopAsyncIteration):
        await anext(disconnected.body_iterator)


@pytest.mark.asyncio
async def test_gui_stream_waits_when_no_view(monkeypatch) -> None:
    monkeypatch.setattr(gui, "_view_model", None)

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(gui.asyncio, "sleep", no_sleep)
    response = await gui.stream(_Request([False, True]))
    with pytest.raises(StopAsyncIteration):
        await anext(response.body_iterator)


def _state(step=0) -> ReplayState:
    return ReplayState("series", 1, step, 3, None, True, "", True)


@pytest.mark.asyncio
async def test_replay_routes_report_unavailable_states(monkeypatch) -> None:
    monkeypatch.setattr(replay, "replay_app_instance", None)
    assert "Replay Viewer" in (await replay.index()).body.decode()
    status = json.loads((await replay.status()).body)
    assert status == {"verified": False, "tamper_reason": "No replay loaded"}
    for route in (
        replay.current,
        replay.next_step,
        replay.prev_step,
        replay.first_step,
        replay.last_step,
    ):
        response = await route()
        assert response.status_code == 503
        assert json.loads(response.body)["error"] == "No replay loaded"


@pytest.mark.asyncio
async def test_replay_routes_delegate_and_serialize_state(monkeypatch) -> None:
    instance = MagicMock()
    instance.verification_status.return_value = (True, "")
    instance.current_state.return_value = _state(0)
    instance.next.return_value = _state(1)
    instance.prev.return_value = _state(0)
    instance.first.return_value = _state(0)
    instance.last.return_value = _state(2)
    monkeypatch.setattr(replay, "replay_app_instance", instance)

    assert json.loads((await replay.status()).body)["verified"] is True
    results = [
        json.loads((await replay.current()).body),
        json.loads((await replay.next_step()).body),
        json.loads((await replay.prev_step()).body),
        json.loads((await replay.first_step()).body),
        json.loads((await replay.last_step()).body),
    ]
    assert [item["step"] for item in results] == [0, 1, 0, 0, 2]
    assert replay._state_to_dict(_state())["game_uid"] == "series"
    assert "<!DOCTYPE html>" in replay._replay_html()
