"""Pins rule-47 enclosure in human-vs-model play (operator-found bug).

The play engine declared 'survival' for a fully walled-in thief; the
production domain captures it where it stands (STAY does not rescue).
"""

from __future__ import annotations

from cop_worker.gui.play_engine import _rule47


def _game(thief, barriers):
    return {
        "thief": list(thief),
        "barriers": [list(b) for b in barriers],
        "over": False,
        "outcome": None,
    }


def test_sealed_corner_is_a_capture():
    # thief at (0,0); both exits walled — the operator's exact scenario
    g = _game((0, 0), [(1, 0), (0, 1)])
    _rule47(g)
    assert g["over"] is True and g["outcome"] == "capture"


def test_one_open_exit_is_not_a_capture():
    g = _game((0, 0), [(1, 0)])
    _rule47(g)
    assert g["over"] is False


def test_center_enclosure_captures():
    g = _game((3, 3), [(2, 3), (4, 3), (3, 2), (3, 4)])
    _rule47(g)
    assert g["over"] is True and g["outcome"] == "capture"


def test_already_over_game_is_untouched():
    g = _game((0, 0), [(1, 0), (0, 1)])
    g["over"], g["outcome"] = True, "survival"
    _rule47(g)
    assert g["outcome"] == "survival"  # never rewrites a settled game
