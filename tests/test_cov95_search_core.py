"""Cover the determinized value-search primitives in research_evaluation.search_core."""

from __future__ import annotations

import math
import random

from cop_worker.domain.types import DomainState
from cop_worker.rl.research_evaluation.search_core import (
    _determinized_value,
    _fast_legal,
    _hypothetical_state,
    _leaf_value,
)
from cop_worker.rl.train_recurrent import _initial_state


def test_hypothetical_state_swaps_opponent_position():
    state = _initial_state(random.Random(1), random_start=False)
    cop_view = _hypothetical_state(state, "cop", (5, 5))
    assert cop_view.thief_position == (5, 5)
    thief_view = _hypothetical_state(state, "thief", (1, 1))
    assert thief_view.cop_position == (1, 1)


def test_leaf_value_is_zero_sum():
    state = _initial_state(random.Random(2), random_start=False)
    assert _leaf_value(state, "cop") == -_leaf_value(state, "thief")


def test_fast_legal_matches_role():
    state = _initial_state(random.Random(3), random_start=False)
    cop_moves = _fast_legal(state, "cop")
    thief_moves = _fast_legal(state, "thief")
    assert all(isinstance(m, str) for m in cop_moves)
    assert "STAY" in thief_moves


def test_determinized_value_depth_and_recursion():
    state = _initial_state(random.Random(5), random_start=False)
    shallow = _determinized_value(state, "cop", depth=1)
    deep = _determinized_value(state, "cop", depth=2)
    assert math.isfinite(shallow) and math.isfinite(deep)


def test_determinized_value_hits_terminal_leaf():
    # Cop adjacent to thief -> at least one joint action captures, exercising
    # the terminal-value branch inside the inner search.
    state = DomainState(
        turn=3,
        grid_size=7,
        cop_position=(3, 3),
        thief_position=(3, 4),
        cop_barriers_remaining=0,
    )
    value = _determinized_value(state, "cop", depth=1)
    assert math.isfinite(value)
