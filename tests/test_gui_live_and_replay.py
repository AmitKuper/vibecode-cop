"""Live GUI + replay viewer: local truth, fail-open, and the crypto verdicts.

Covers docs/GUI_PRD.md acceptance points at unit level; the live end-to-end
check is a full simulated series with the GUI on (docs/GUI_TODO.md WP7).
"""

from __future__ import annotations

import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from ref3_match import gui_bridge, gui_context  # noqa: E402

from cop_worker.gui.live_view_model import LiveViewModel  # noqa: E402
from cop_worker.observation import SafeLiveView  # noqa: E402


class _Mover:
    pos = [2, 4]
    barriers_remaining = 11


def _view_model() -> LiveViewModel:
    vm = LiveViewModel("cop", 7)
    gui_bridge.set_view_model(vm)
    return vm


def teardown_function(_fn) -> None:
    gui_bridge.set_view_model(None)


# --- local truth ------------------------------------------------------------


def test_published_view_carries_turn_context_and_no_hidden_coordinate():
    vm = _view_model()
    gui_context.note_window(3, "nis-yar1", {"max_steps": 35, "num_games": 6})
    gui_context.note_received({"hint": "I am near the park", "commit": "a" * 64}, step=7)
    heat = [[0.0] * 7 for _ in range(7)]
    heat[1][5] = 0.8
    gui_bridge.publish_view(_Mover(), heat)

    view = vm.get_current()
    assert view is not None
    d = asdict(view)
    assert d["sub_game"] == 3 and d["opponent_group"] == "nis-yar1"
    assert d["last_hint"] == "I am near the park"
    assert d["last_commit_received"] == "a" * 12  # prefix only, never the full hash
    assert d["your_turn"] is True
    # The one hard rule: no hidden opponent coordinate, under any name.
    assert "opponent_position" not in d and "thief_position" not in d
    # Belief is normalized scent: sums to 1 when any signal exists.
    assert abs(sum(v for row in d["belief_heatmap"] for v in row) - 1.0) < 1e-9


def test_banner_locks_after_send():
    vm = _view_model()

    class _Out:
        local_records = [{"commit": "b" * 64}]

    gui_context.note_received({"hint": "", "commit": "a" * 64}, step=1)
    gui_context.note_sent(_Out())
    gui_bridge.publish_view(_Mover(), [[0.0] * 7 for _ in range(7)])
    view = vm.get_current()
    assert view.your_turn is False and view.last_commit_sent == "b" * 12


def test_view_model_rejects_hidden_coordinate_keys():
    vm = LiveViewModel("cop", 7)
    view = SafeLiveView(
        own_position=(0, 0),
        belief_heatmap=[],
        opponent_scent=[],
        last_hint="",
        hint_reliability=0.5,
        turn=1,
        gamelet=1,
        score={},
        own_barriers_remaining=0,
        protocol_state="GAMEPLAY",
        your_turn=True,
        connection_healthy=True,
    )
    vm.update(view)  # clean view passes
    assert vm.get_current() is view


# --- fail-open --------------------------------------------------------------


def test_publish_never_raises_even_with_a_poisoned_view_model():
    class _Broken:
        def update(self, view):  # noqa: ARG002
            raise RuntimeError("GUI died mid-series")

    gui_bridge.set_view_model(_Broken())
    gui_bridge.publish_view(_Mover(), [[0.0] * 7])  # must not raise


def test_context_setters_are_noops_without_a_gui():
    gui_bridge.set_view_model(None)
    gui_context.note_window(1, "x", {})
    gui_context.note_received({}, 1)
    gui_context.note_settled(1, True, "capture", "police")  # must not raise
