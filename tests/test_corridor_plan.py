"""Pins the corridor plan (the cop's line-partition strategy)."""

from __future__ import annotations

from cop_worker.rl.corridor_plan import MIN_BUDGET, MIN_STEP, STABLE_TURNS, CorridorPlan

LEGAL = ["N", "S", "E", "W", "STAY", "PLACE_N", "PLACE_S", "PLACE_E", "PLACE_W"]


def _stall(plan, cop, thief, turns, step0=MIN_STEP, b_left=14):
    out = None
    for i in range(turns):
        out = plan.override(cop, thief, [], b_left, step0 + i, LEGAL)
    return out


def test_never_fires_early_or_during_convergence():
    plan = CorridorPlan()
    # converging distances (5,4,3,2 ...) never trip the oscillation window
    for step, d in enumerate([6, 5, 4, 3, 2, 2], start=1):
        assert plan.override((0, 0), (d, 0), [], 14, step, LEGAL) is None


def test_never_fires_at_capture_in_hand():
    plan = CorridorPlan()
    _stall(plan, (3, 2), (3, 4), STABLE_TURNS + 2)
    assert plan.override((3, 3), (3, 4), [], 14, MIN_STEP + 9, LEGAL) is None


def test_never_fires_without_wall_budget():
    plan = CorridorPlan()
    assert _stall(plan, (3, 2), (3, 5), STABLE_TURNS + 2, b_left=MIN_BUDGET - 1) is None


def test_fires_on_sustained_oscillation_and_builds_the_line():
    plan = CorridorPlan()
    act = _stall(plan, (2, 3), (5, 3), STABLE_TURNS + 1)
    assert act is not None
    # thief east at x=5 -> line x=3, guard x=2: cop is on the guard lane, so
    # the first plan action is a placement toward the line (east)
    assert act == "PLACE_E"


def test_goes_silent_once_line_stands():
    plan = CorridorPlan()
    _stall(plan, (2, 3), (5, 3), STABLE_TURNS + 1)
    # line x=3 fully built except one door -> plan hands over to the hunt
    walls = [(3, y) for y in range(6)]  # (3,6) stays open as the door
    act = plan.override((2, 3), (5, 3), walls, 8, MIN_STEP + 10, LEGAL)
    assert act is None and plan._done is True
    # and it stays silent afterwards
    assert plan.override((2, 3), (5, 3), walls, 8, MIN_STEP + 11, LEGAL) is None


def test_reset_clears_plan_state():
    plan = CorridorPlan()
    _stall(plan, (2, 3), (5, 3), STABLE_TURNS + 1)
    plan.reset()
    assert plan._active is False and plan._dists == []
