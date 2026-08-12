"""Targeted tests for modules the 2026-08-10 additions left under the CI coverage gate.

This part pins the small pure utilities: phase tracker, live view model, dual logging.
"""

from __future__ import annotations

import logging

# ---------------------------------------------------------------------------
# cop_worker.mcp.protocol_phases
# ---------------------------------------------------------------------------
from cop_worker.mcp.protocol import ProtocolPhase
from cop_worker.mcp.protocol_phases import StepPhaseTracker


class TestStepPhaseTracker:
    def test_both_at_phase_requires_both_roles(self) -> None:
        tracker = StepPhaseTracker()
        phase = list(ProtocolPhase)[0]
        assert tracker.both_at_phase(1, phase) is False
        tracker.mark_phase(1, "cop", phase)
        assert tracker.both_at_phase(1, phase) is False
        tracker.mark_phase(1, "police", phase)
        assert tracker.both_at_phase(1, phase) is True
        assert tracker.to_dict() == {1: {"cop": phase.value, "police": phase.value}}


# ---------------------------------------------------------------------------
# cop_worker.gui.live_view_model
# ---------------------------------------------------------------------------
from cop_worker.gui.live_view_model import LiveViewModel
from cop_worker.observation import SafeLiveView


def _view() -> SafeLiveView:
    return SafeLiveView(
        own_position=(1, 2),
        belief_heatmap=[[1.0 / 49] * 7 for _ in range(7)],
        opponent_scent=[[0.0] * 7 for _ in range(7)],
        last_hint="",
        hint_reliability=0.5,
        turn=3,
        gamelet=1,
        score={"cop": 0, "thief": 0},
        own_barriers_remaining=14,
        protocol_state="PLAYING",
        your_turn=True,
        connection_healthy=True,
    )


class TestLiveViewModel:
    def test_update_then_read_round_trips_without_hidden_coords(self) -> None:
        model = LiveViewModel("cop", 7)
        assert model.get_current() is None
        assert model.get_update() is None
        model.update(_view())
        assert model.get_current().own_position == (1, 2)
        update = model.get_update()
        assert update is not None
        payload = update.to_json()
        assert '"turn": 3' in payload


# ---------------------------------------------------------------------------
# cop_worker.logging_setup
# ---------------------------------------------------------------------------
from cop_worker.logging_setup import setup_dual_logging


class TestDualLogging:
    def test_creates_timestamped_file_and_logs_to_it(self, tmp_path) -> None:
        root = logging.getLogger()
        previous = root.handlers[:]
        try:
            log_file = setup_dual_logging(prefix="covtest", log_dir=tmp_path)
            logging.getLogger("covtest").info("hello coverage")
            for handler in root.handlers:
                handler.flush()
            assert log_file.exists()
            assert "hello coverage" in log_file.read_text(encoding="utf-8")
        finally:
            for handler in root.handlers[:]:
                if handler not in previous:
                    handler.close()
                    root.removeHandler(handler)
            for handler in previous:
                if handler not in root.handlers:
                    root.addHandler(handler)
