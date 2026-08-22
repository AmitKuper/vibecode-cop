"""Pins the sighted-under-book path (book-scent pairing prep, 2026-08-21).

Under a locked ``multiplicative_book_v1`` the raw field saturates by ~step 10
and the chebyshev tracker goes blind; with ``decode_book_scent`` the search
policy inverts the clamped law and stays sighted the whole game. Chebyshev
pairings (decode off, the default) must resolve byte-identically to before.
"""

from __future__ import annotations

import numpy as np

from cop_worker.rl.opponent_fix import OpponentFix
from cop_worker.rl.pursuit_search import best_cop_action
from cop_worker.rl.search_policy import SearchRolePolicy
from cop_worker.rl.search_wrap import wrap_with_search
from tests.helpers_scent_decoder import GRID, _wire_step

LEGAL = ["N", "S", "E", "W", "STAY", "PLACE_N", "PLACE_S", "PLACE_E", "PLACE_W"]


def _book_walk(steps: int, start=(3, 3)):
    """Book-law fields for a deterministic east-then-south walk; yields (field, pos)."""
    field = np.zeros((GRID, GRID))
    pos = start
    moves = [(1, 0), (0, 1)] * (steps // 2 + 1)
    for i in range(steps):
        dx, dy = moves[i]
        pos = (min(GRID - 1, pos[0] + dx), min(GRID - 1, pos[1] + dy))
        field = _wire_step(field, pos)
        yield field.tolist(), pos


def test_fix_follows_emitter_through_the_saturated_plateau():
    fix = OpponentFix(decode_book=True)
    for step, (grid, pos) in enumerate(_book_walk(20), start=1):
        assert fix.fix(grid, GRID) == pos, f"lost the emitter at step {step}"


def test_decode_off_is_blind_on_book_plateau():
    # pre-decoder behavior (chebyshev pairings): once the plateau kills the
    # unique 0.9 peak, the fix freezes on a stale coasted cell and never
    # recovers — proving decode_book is what closes the gap, and that the
    # default path takes no new code route.
    frames = list(_book_walk(15))
    blind = OpponentFix(decode_book=False)
    fixes = [blind.fix(grid, GRID) for grid, _pos in frames]
    assert fixes[-1] != frames[-1][1]


def test_reset_clears_decoder_state():
    fix = OpponentFix(decode_book=True)
    for grid, _pos in _book_walk(6):
        fix.fix(grid, GRID)
    fix.reset()
    # a fresh sub-game from a zero field decodes exactly again
    fresh = _wire_step(np.zeros((GRID, GRID)), (0, 3))
    assert fix.fix(fresh.tolist(), GRID) == (0, 3)


def test_search_policy_plays_sighted_minimax_under_book_scent():
    from cop_worker.observation import BeliefState, LocalObservation

    policy = SearchRolePolicy("cop", depth=3, decode_book_scent=True)
    frames = list(_book_walk(14))
    action = None
    for step, (grid, _pos) in enumerate(frames, start=1):
        obs = LocalObservation(
            own_position=(0, 0),
            own_barriers_remaining=14,
            known_barriers=[],
            opponent_scent=grid,
            last_hint="",
            step=step,
            gamelet=1,
            grid_size=GRID,
        )
        action = policy.select_action(obs, BeliefState.uniform(GRID, step=step), LEGAL)
    true_thief = frames[-1][1]
    expected = best_cop_action((0, 0), true_thief, [], 14, 35 - len(frames) + 1, depth=3, n=GRID)
    assert action == expected  # sighted search on the DECODED cell, not a fallback


def test_wrap_passes_scent_model_through():
    wrapped = wrap_with_search(None, "police", {}, scent_model="multiplicative_book_v1")
    assert wrapped._fix.decode_book is True
    default = wrap_with_search(None, "police", {}, scent_model="subtractive_chebyshev_v1")
    assert default._fix.decode_book is False
    legacy = wrap_with_search(None, "police", {})
    assert legacy._fix.decode_book is False
