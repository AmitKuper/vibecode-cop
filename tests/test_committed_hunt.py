"""Pins CommittedHunt (the operator's cage strategy as a cop plan).

Measured 2026-08-22 (corridor_lab, 5s budgets, idle): the hunt chain is the
only cop that captures the confined thief (@31); the wire default keeps the
corridor chain (mirror-evade coverage). These tests pin the plan's gates
and phases, not the full-game outcomes — the labs own those.
"""

from __future__ import annotations

from cop_worker.rl.committed_hunt import FUSE, CommittedHunt

LEGAL = [
    "N", "S", "E", "W", "STAY",
    "PLACE_N", "PLACE_S", "PLACE_E", "PLACE_W",
]  # fmt: skip


def _stall(hunt, cop, thief, turns, barriers=(), b_left=14, steps_left=30):
    """Feed ``turns`` no-progress turns; return the last override result."""
    out = None
    for _ in range(turns):
        out = hunt.override(cop, thief, list(barriers), b_left, steps_left, LEGAL)
    return out


def test_silent_while_converging():
    hunt = CommittedHunt()
    # distance shrinks every turn: net progress -> never commits
    for d0 in range(6, 1, -1):
        assert hunt.override((0, 0), (d0, 0), [], 14, 30, LEGAL) is None
    assert hunt._line is None


def test_commits_after_fuse_and_builds():
    hunt = CommittedHunt()
    out = _stall(hunt, (2, 3), (4, 3), FUSE + 1)
    assert hunt._line is not None
    assert out is not None  # walking the stand lane or placing


def test_oscillation_counts_as_no_progress():
    hunt = CommittedHunt()
    # the dance: d alternates 2/3 — min_d never improves after the first
    for i in range(FUSE + 2):
        thief = (4, 3) if i % 2 == 0 else (4, 2)
        hunt.override((2, 3), thief, [], 14, 30, LEGAL)
    assert hunt._line is not None


def test_capture_in_hand_defers():
    hunt = CommittedHunt()
    _stall(hunt, (2, 3), (4, 3), FUSE + 1)
    assert hunt.override((4, 2), (4, 3), [], 14, 20, LEGAL) is None  # d=1


def test_no_budget_no_commit():
    hunt = CommittedHunt()
    assert _stall(hunt, (2, 3), (4, 3), FUSE + 1, b_left=3) is None
    assert hunt._line is None


def test_no_time_no_commit():
    hunt = CommittedHunt()
    assert _stall(hunt, (2, 3), (4, 3), FUSE + 1, steps_left=10) is None
    assert hunt._line is None


def test_endgame_only_never_builds_a_line():
    hunt = CommittedHunt(endgame_only=True)
    _stall(hunt, (2, 3), (4, 3), FUSE + 1)
    assert hunt._line == []  # committed, but cut-walls only


def test_endgame_only_requires_close_range():
    hunt = CommittedHunt(endgame_only=True)
    assert _stall(hunt, (0, 0), (6, 6), FUSE + 1) is None  # d=12: no cage
    assert hunt._line is None


def test_line_mirrors_to_the_thiefs_half():
    north, south = CommittedHunt(), CommittedHunt()
    _stall(north, (2, 1), (4, 1), FUSE + 1)
    _stall(south, (2, 5), (4, 5), FUSE + 1)
    assert all(y <= 3 for _x, y in north._line)
    assert all(y >= 3 for _x, y in south._line)


def test_reset_clears_the_commitment():
    hunt = CommittedHunt()
    _stall(hunt, (2, 3), (4, 3), FUSE + 1)
    hunt.reset()
    assert hunt._line is None and hunt._evade == 0


def test_places_line_cell_from_the_stand():
    hunt = CommittedHunt()
    _stall(hunt, (2, 3), (4, 3), FUSE + 1)  # line = column x=4, stand x=3
    # thief squats on (4,3): that cell is skipped; from stand (3,4) the
    # build places the next cell (4,4) eastward
    out = hunt.override((3, 4), (4, 3), [], 14, 20, LEGAL)
    assert out == "PLACE_E"


def test_thief_squatting_on_a_line_cell_does_not_deadlock():
    hunt = CommittedHunt()
    _stall(hunt, (2, 3), (4, 3), FUSE + 1)
    # thief squats the first line cell (4,3); the build skips it and walks
    # toward the NEXT cell's stand (3,4) instead of hovering
    out = hunt.override((3, 2), (4, 3), [], 14, 20, LEGAL)
    assert out == "S"


def test_endgame_hunt_places_a_cut_reducing_wall():
    hunt = CommittedHunt(endgame_only=True)
    # corner thief (6,1), cop two away: placing (5,1) shrinks the escape cut
    out = _stall(hunt, (4, 1), (6, 1), FUSE + 2)
    assert out is not None and out.startswith("PLACE_")
    assert hunt._hunt_walls >= 1


def test_hunt_wall_cap_is_respected():
    hunt = CommittedHunt(endgame_only=True)
    _stall(hunt, (4, 1), (6, 1), FUSE + 1)
    hunt._hunt_walls = 99
    assert hunt.override((4, 1), (6, 1), [], 14, 20, LEGAL) is None
