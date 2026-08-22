"""Pins the stall-squeeze barrier override (anti-evader wall placement)."""

from cop_worker.rl.stall_squeeze import STALL_TURNS, StallSqueeze, survival_layers

LEGAL = ["N", "S", "E", "W", "STAY", "PLACE_N", "PLACE_S", "PLACE_E", "PLACE_W"]


def _stall(sq, cop, thief, turns, barriers=(), b_left=14, steps_left=25):
    out = None
    for _ in range(turns):
        out = sq.override(cop, thief, list(barriers), b_left, steps_left, LEGAL)
    return out


def test_open_board_is_thief_win_everywhere():
    layers, idx = survival_layers(frozenset(), 7)
    assert layers[35][idx[(0, 0)]][idx[(3, 3)]] is True
    assert all(layers[35][idx[(0, 0)]][t] for p, t in idx.items() if p != (0, 0))


def test_no_fire_before_stall_threshold():
    sq = StallSqueeze()
    assert _stall(sq, (3, 2), (3, 4), STALL_TURNS - 1) is None


def test_fires_on_counted_game_stall_pattern():
    # the exact SMNGRP05 mirror state: cop (3,2), thief (3,4), distance 2
    sq = StallSqueeze()
    action = _stall(sq, (3, 2), (3, 4), STALL_TURNS + 1)
    assert action is not None and action.startswith("PLACE_")


def test_place_name_matches_production_convention():
    # cop (3,2), thief (3,4): the only improving wall is the between-cell
    # (3,3) = cop + (0,1) = PLACE_S under action_space/domain conventions.
    # Pins the delta->name seam (a hand-typed map once rotated it to PLACE_E).
    from cop_worker.rl.action_space import PLACE_DIRS
    from cop_worker.rl.stall_squeeze import _PLACE

    assert {tuple(d): a for a, d in PLACE_DIRS.items()} == _PLACE
    sq = StallSqueeze()
    assert _stall(sq, (3, 2), (3, 4), STALL_TURNS + 1) == "PLACE_S"


def test_capture_in_hand_never_preempted():
    # adjacent thief (d=1) = capture this half-move; hook must stay silent
    # even with a saturated stall counter
    sq = StallSqueeze()
    _stall(sq, (3, 2), (3, 4), STALL_TURNS + 2)
    assert sq.override((3, 3), (3, 4), [], 14, 20, LEGAL) is None


def test_strict_improvement_required():
    # thief far away and unstable distances -> stall never accumulates
    sq = StallSqueeze()
    assert sq.override((0, 0), (6, 6), [], 14, 30, LEGAL) is None
    assert sq.override((0, 0), (5, 5), [], 14, 30, LEGAL) is None


def test_no_fire_without_barriers():
    sq = StallSqueeze()
    assert _stall(sq, (3, 2), (3, 4), STALL_TURNS + 1, b_left=0) is None


def test_reset_clears_stall_state():
    sq = StallSqueeze()
    _stall(sq, (3, 2), (3, 4), STALL_TURNS - 1)
    sq.reset()
    assert _stall(sq, (3, 2), (3, 4), 1) is None


def test_wall_cap_respected():
    sq = StallSqueeze()
    sq._hook_walls = 8  # MAX_HOOK_WALLS
    assert _stall(sq, (3, 2), (3, 4), STALL_TURNS + 1) is None


def test_never_walls_last_exit():
    # cop in a corner with (0,1) already walled: its only exit is (1,0);
    # any placement would leave <2 exits, so the hook must refuse
    sq = StallSqueeze()
    assert _stall(sq, (0, 0), (0, 2), STALL_TURNS + 2, barriers=[(0, 1)]) is None
    act = sq.override((0, 0), (2, 0), [(0, 1)], 13, 20, LEGAL)
    assert act is None


def test_never_walls_the_cop_out_of_the_thiefs_region():
    """Counted g02 vs cosmos77 (2026-08-22), step 23: cop (5,0), thief (3,0),
    hook walls already at (4,1),(3,2),(2,2),(1,3),(2,4),(3,4). PLACE_W onto
    (4,0) shrank the thief's surviving-move set AND raised the cop's own BFS
    path to the thief from 2 to 10+ — the cop then chased a 16-step detour
    with 12 steps left. The self-cutoff guard must refuse that wall."""
    walls = [(4, 1), (3, 2), (2, 2), (1, 3), (2, 4), (3, 4)]
    sq = StallSqueeze()
    out = _stall(sq, (5, 0), (3, 0), STALL_TURNS + 2, barriers=walls, b_left=8)
    assert out != "PLACE_W"


def test_guard_allows_walls_that_keep_the_path():
    """The guard must not kill the hook: the SMNGRP05 mirror wall (3,3) keeps
    bfs(cop, thief) at 2 and still fires."""
    sq = StallSqueeze()
    assert _stall(sq, (3, 2), (3, 4), STALL_TURNS + 1) == "PLACE_S"
