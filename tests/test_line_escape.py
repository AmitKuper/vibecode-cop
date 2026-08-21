"""Pins the confined-mode thief (anti-partition, yanell11 postmortem 2026-08-21)."""

from __future__ import annotations

from cop_worker.rl.line_escape import LineEscape, _threat_line

LEGAL = ["N", "S", "E", "W", "STAY"]


def test_silent_with_no_walls():
    esc = LineEscape()
    assert esc.override((5, 3), (1, 1), [], 14, 30, "N", LEGAL) is None


def test_silent_with_scattered_non_line_walls():
    esc = LineEscape()
    walls = [(1, 1), (5, 5)]  # no two collinear on an interior line
    assert _threat_line(frozenset(walls), 12, 7) is False
    assert esc.override((5, 3), (1, 1), walls, 12, 30, "N", LEGAL) is None


def test_threat_detected_on_forming_line():
    # the recorded yanell11 sweep: walls marching down x=3
    assert _threat_line(frozenset({(3, 0), (3, 1)}), 12, 7) is True


def test_no_threat_when_budget_cannot_complete():
    walls = frozenset({(3, 0), (3, 1)})
    assert _threat_line(walls, 2, 7) is False  # 5 open cells, 2 walls left


def test_edge_line_is_not_a_partition():
    assert _threat_line(frozenset({(0, 2), (0, 3)}), 12, 7) is False


def test_confined_mode_prefers_surviving_mobile_cells():
    # line forming at x=3; thief east at (5,3), cop west at (2,3): every move
    # survives the CURRENT walls, so mobility decides — the center-most cell
    # (5,3)->stay has mobility 4, but (4,3)/(6,3) differ; assert the choice is
    # a legal surviving move and NOT a corner-seeking one.
    esc = LineEscape()
    walls = [(3, 0), (3, 1), (3, 2)]
    move = esc.override((5, 3), (2, 3), walls, 11, 25, "E", LEGAL)
    assert move in {"N", "S", "W", "STAY", None}  # never pushed toward x=6 corner line


def test_returns_none_when_agreeing_with_minimax():
    esc = LineEscape()
    walls = [(3, 0), (3, 1), (3, 2)]
    chosen = esc.override((5, 3), (2, 3), walls, 11, 25, "E", LEGAL)
    if chosen is not None:
        # calling again with planned == its own choice must return None
        assert esc.override((5, 3), (2, 3), walls, 11, 25, chosen, LEGAL) is None


def test_reset_clears_table_cache():
    esc = LineEscape()
    esc.override((5, 3), (2, 3), [(3, 0), (3, 1)], 12, 25, "E", LEGAL)
    esc.reset()
    assert esc._cache == {}
