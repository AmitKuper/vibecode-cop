"""Fast contract tests for isolated RL research helpers."""

from __future__ import annotations

import random

import numpy as np
import torch

from cop_worker.belief_engine import BeliefEngine
from cop_worker.rl.research_evaluation import (
    ScriptedResearchPolicy,
    _fast_legal,
    belief_search_scores,
    play_game,
)
from cop_worker.rl.research_value_training import DuelingDoubleQNetwork
from cop_worker.rl.train_recurrent import _initial_state, _legal


def test_inner_search_legality_matches_canonical_transition() -> None:
    state = _initial_state(random.Random(1), random_start=False, grid_size=7)
    for role in ("cop", "thief"):
        assert _fast_legal(state, role) == _legal(state, role)


def test_belief_search_does_not_consult_real_hidden_opponent_position() -> None:
    state = _initial_state(random.Random(1), random_start=False, grid_size=7)
    moved_hidden = state.model_copy(update={"thief_position": (6, 6)})
    belief = BeliefEngine(7, "cop")
    legal = _legal(state, "cop")
    first = belief_search_scores(state, "cop", belief, legal, max_particles=3)
    second = belief_search_scores(moved_hidden, "cop", belief, legal, max_particles=3)
    assert first == second


def test_canonical_research_game_terminates_with_official_score() -> None:
    cop = ScriptedResearchPolicy("cop", "anti_loop")
    thief = ScriptedResearchPolicy("thief", "random")
    result = play_game(cop, thief, seed=17, random_start=False)
    assert result.winner in {"cop", "thief"}
    assert 1 <= result.turns <= 35
    assert (result.cop_score, result.thief_score) in {(20, 5), (5, 10)}


def test_dueling_double_q_shape_and_finite_values() -> None:
    network = DuelingDoubleQNetwork(201, 9, hidden_size=16)
    values = network(torch.tensor(np.zeros((3, 201)), dtype=torch.float32))
    assert values.shape == (3, 9)
    assert bool(torch.isfinite(values).all())
