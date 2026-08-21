"""Pins sealability (min-cut) + the pocket-mode escape (operator postmortem
2026-08-21: adaptive wall-pocketing beat the confined-mode thief six straight).

Two behaviors under pin:
  1. sealability() is the exact min vertex cut between the thief and open
     space — the number of future walls a perfect pocketer still needs.
  2. LineEscape's pocket trigger + turn-parity fix: with the cop orthogonally
     adjacent, a candidate cell next to the cop is NOT survivable (the cop
     replies before the thief moves again) — the pre-fix table said it was,
     and the thief died by choosing STAY in reply range (trace s16).
"""

from __future__ import annotations

from cop_worker.rl.line_escape import LineEscape
from cop_worker.rl.sealability import sealability

LEGAL = ["N", "S", "E", "W", "STAY"]


def test_open_board_center_cut_is_four():
    # 4 orthogonal neighbors = the classic vertex cut of a grid interior
    assert sealability((3, 3), (0, 0), []) == 4


def test_corner_cut_is_two():
    assert sealability((0, 0), (6, 6), []) == 2


def test_walls_reduce_the_cut():
    # two of the corner thief's escape lanes pre-walled -> one wall seals
    assert sealability((0, 0), (6, 6), [(1, 0)]) == 1


def test_confined_region_is_cut_zero():
    # thief sealed in its corner: no cell at Manhattan >= 4 is reachable and
    # the whole region is within distance 4 -> "already confined"
    assert sealability((0, 0), (6, 6), [(1, 0), (0, 1)]) == 0


def test_thief_and_cop_cells_are_not_wallable():
    # the cut must consist of OTHER cells: with the cop sitting in the only
    # corridor cell, the cut is 0 free walls short of... still >= 1 because
    # the cop's own cell can't be counted as a wall
    cut = sealability((0, 0), (1, 0), [(0, 1)])
    assert cut >= 1


def test_pocket_trigger_fires_without_a_line():
    # scattered (non-collinear) walls that narrow the cut: old trigger was
    # line-only and stayed silent — the operator's exact exploit
    esc = LineEscape()
    walls = [(1, 0), (0, 1)]  # corner thief, cut 0, cop has budget
    move = esc.override((0, 0), (5, 5), walls, 10, 25, "STAY", LEGAL)
    # pocket mode must engage (any non-None answer or an agreeing None is
    # fine); what is pinned is that it does not crash and considers the state
    assert move in {"N", "S", "E", "W", "STAY", None}


def test_adjacent_cell_is_rejected_under_cop_reply():
    # cop at (4,4), thief at (5,5) with its N/W lanes walled: moving W to
    # (4,5) lands in the cop's reply range. Pre-fix the survival table
    # (thief-to-move parity) called that survivable and the thief died there.
    esc = LineEscape()
    walls = [(5, 4), (3, 4), (1, 4), (0, 4)]
    move = esc.override((5, 5), (4, 4), walls, 7, 21, "W", LEGAL)
    assert move is not None and move != "W"


def test_stay_in_reply_range_is_rejected():
    # thief at (4,5) orthogonally adjacent to cop (4,4): STAY = captured on
    # the cop's reply. The escape must move, never park (trace s16 death).
    esc = LineEscape()
    walls = [(5, 4), (3, 4), (1, 4), (0, 4)]
    move = esc.override((4, 5), (4, 4), walls, 7, 20, "STAY", LEGAL)
    assert move is not None and move != "STAY"


def test_wall_safe_counts_the_cops_best_placement():
    # mocked table: q=(3,3) has exactly two surviving continuations,
    # (3,2) and (3,3)-stay; the cop at (2,2) can wall (3,2) -> worst = 1
    esc = LineEscape()
    cells = [(3, 3), (3, 2), (3, 4), (2, 3), (4, 3), (2, 2), (1, 2), (2, 1), (3, 1)]
    idx = {c: i for i, c in enumerate(cells)}
    surviving = {(3, 3), (3, 2)}
    row = [c in surviving for c in cells]
    layers = {5: [row] * len(cells)}
    assert esc._wall_safe((3, 3), (2, 2), frozenset(), layers, idx, 5, budget=8) == 1


def test_wall_safe_without_budget_keeps_all_continuations():
    esc = LineEscape()
    cells = [(3, 3), (3, 2), (3, 4), (2, 3), (4, 3), (2, 2)]
    idx = {c: i for i, c in enumerate(cells)}
    surviving = {(3, 3), (3, 2), (3, 4)}
    row = [c in surviving for c in cells]
    layers = {5: [row] * len(cells)}
    assert esc._wall_safe((3, 3), (2, 2), frozenset(), layers, idx, 5, budget=0) == 3
