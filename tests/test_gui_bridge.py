"""Live-GUI bridge: publish hook feeds the view model; off/failure paths are inert."""

from __future__ import annotations

import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from cop_worker.gui.live_view_model import LiveViewModel

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from ref3_match import gui_bridge  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_bridge():
    gui_bridge.set_view_model(None)
    yield
    gui_bridge.set_view_model(None)


def _mover(pos=(2, 3), grid=7, barriers=2):
    return SimpleNamespace(pos=list(pos), grid=grid, barriers_remaining=barriers, role="police")


def _heatmap(n=7, hot=(4, 1), value=0.9):
    g = [[0.0] * n for _ in range(n)]
    g[hot[0]][hot[1]] = value
    return g


def test_publish_updates_registered_view_model() -> None:
    vm = LiveViewModel("cop", 7)
    gui_bridge.set_view_model(vm)
    gui_bridge.publish_view(_mover(pos=(2, 3)), _heatmap())
    view = vm.get_current()
    assert view is not None
    assert view.own_position == (3, 2)  # [x, y] -> wire (row, col)
    # belief is the sensed field NORMALIZED to a probability surface (GUI_PRD R3);
    # the raw value lives in opponent_scent.
    assert view.belief_heatmap[4][1] == 1.0
    assert view.opponent_scent[4][1] == 0.9
    assert view.turn == 1
    gui_bridge.publish_view(_mover(pos=(2, 4)), _heatmap())
    assert vm.get_current().turn == 2
    assert vm.get_current().own_position == (4, 2)


def test_disabled_path_is_a_noop() -> None:
    gui_bridge.set_view_model(None)
    # Must not raise and must not need any mover attributes beyond the None check.
    gui_bridge.publish_view(_mover(), _heatmap())
    gui_bridge.publish_view(None, None)


def test_gui_failure_never_propagates_to_play() -> None:
    class _Exploding:
        def update(self, view):
            raise RuntimeError("GUI died")

    gui_bridge.set_view_model(_Exploding())
    gui_bridge.publish_view(_mover(), _heatmap())  # must swallow the failure


def test_no_hidden_coordinate_ever_published() -> None:
    vm = LiveViewModel("cop", 7)
    gui_bridge.set_view_model(vm)
    gui_bridge.publish_view(_mover(), _heatmap())
    view_dict = asdict(vm.get_current())
    for forbidden in ("opponent_position", "thief_position", "cop_position"):
        assert forbidden not in view_dict


def test_verify_no_hidden_coord_invariant_still_enforced() -> None:
    """The view model still rejects any view that carries a hidden coordinate."""

    @dataclass(frozen=True)
    class _LeakyView:
        own_position: tuple
        opponent_position: tuple

    vm = LiveViewModel("cop", 7)
    with pytest.raises(ValueError, match="Hidden coordinate"):
        vm.update(_LeakyView(own_position=(0, 0), opponent_position=(5, 5)))


async def test_maybe_start_gui_absent_port_returns_none() -> None:
    assert await gui_bridge.maybe_start_gui("police", {}) is None
    assert await gui_bridge.maybe_start_gui("thief", {"gui_port": "8781"}) is None
    assert await gui_bridge.maybe_start_gui("thief", {"gui_port": True}) is None
    # And nothing got registered, so publishing stays a no-op.
    gui_bridge.publish_view(_mover(), _heatmap())


def test_stop_gui_clears_view_model_and_handles_none() -> None:
    vm = LiveViewModel("cop", 7)
    gui_bridge.set_view_model(vm)
    gui_bridge.stop_gui(None)
    gui_bridge.publish_view(_mover(), _heatmap())
    assert vm.get_current() is None  # cleared before the publish
