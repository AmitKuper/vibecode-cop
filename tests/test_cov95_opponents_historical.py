"""Cover the recurrent-checkpoint branch of _historical_action."""

from __future__ import annotations

import random

import pytest

from cop_worker.belief_engine import BeliefEngine
from cop_worker.rl.action_space import COP_ACTIONS, THIEF_ACTIONS
from cop_worker.rl.recurrent_policy import RecurrentActorCritic
from cop_worker.rl.train_recurrent import _initial_state, _legal
from cop_worker.rl.train_recurrent.opponents_historical import _historical_action

INPUT = 4 * 7 * 7 + 5


def test_historical_action_requires_loaded_policy():
    state = _initial_state(random.Random(1), random_start=False)
    with pytest.raises(RuntimeError, match="not be loaded|not loaded|not.*loaded"):
        _historical_action(state, "cop", _legal(state, "cop"), None, None, None)


def test_historical_recurrent_cop_uses_fallback_scent_and_belief():
    state = _initial_state(random.Random(2), random_start=False)
    net = RecurrentActorCritic(INPUT, len(COP_ACTIONS), 8)
    legal = _legal(state, "cop")
    action = _historical_action(state, "cop", legal, net, opponent_scent=None, opponent_belief=None)
    assert action in legal


def test_historical_recurrent_thief_with_scent_and_belief():
    state = _initial_state(random.Random(3), random_start=False)
    net = RecurrentActorCritic(INPUT, len(THIEF_ACTIONS), 8)
    legal = _legal(state, "thief")
    scent = [[0.1] * state.grid_size for _ in range(state.grid_size)]
    action = _historical_action(
        state,
        "thief",
        legal,
        net,
        opponent_scent=scent,
        opponent_belief=BeliefEngine(state.grid_size, "thief"),
    )
    assert action in legal
