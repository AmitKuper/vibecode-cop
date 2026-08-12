"""Evidence-contract tests for recurrent training — evaluation and opponent families."""

import random
from unittest.mock import patch

import numpy as np
import pytest

from cop_worker.belief_engine import BeliefEngine
from cop_worker.domain.types import DomainState
from cop_worker.observation import BeliefState
from cop_worker.rl.action_space import COP_ACTIONS
from cop_worker.rl.train_recurrent import (
    FAMILIES,
    _belief_expert_action,
    _initial_state,
    _legal,
    _opponent_action,
    evaluate,
)
from tests.helpers_codex_recurrent import _state


def test_evaluation_uses_exact_six_gamelet_series_and_official_scores():
    calls = []

    def fake_episode(*args, **kwargs):
        calls.append((args, kwargs))
        return [], "cop", 7

    with patch("cop_worker.rl.train_recurrent._run_episode", side_effect=fake_episode):
        result = evaluate(
            network=object(),
            role="cop",
            series_per_family=2,
            seed=17,
            historical_policy=object(),
        )

    expected_series = len(FAMILIES) * 2
    expected_gamelets = expected_series * 6
    assert len(calls) == expected_gamelets
    assert result["held_out_series"] == expected_series
    assert result["held_out_games"] == expected_gamelets
    assert result["series_wins"] == expected_series
    assert result["official_role_score"] == expected_gamelets * 20
    assert result["official_opponent_score"] == expected_gamelets * 5
    assert all(item["games"] == 12 for item in result["families"].values())


def test_belief_opponent_action_is_independent_of_hidden_target_coordinate():
    belief = BeliefEngine(7, "cop")
    probability = np.zeros((7, 7))
    probability[2][5] = 1.0
    belief._belief = BeliefState(7, probability, confidence=1.0)

    def state_with_hidden_thief(thief_position):
        return DomainState(
            turn=4,
            grid_size=7,
            cop_position=(3, 3),
            thief_position=thief_position,
            barriers=[],
            cop_barriers_remaining=14,
            move_history=[],
            scent_grid=[[0.0] * 7 for _ in range(7)],
        )

    first = _opponent_action(
        state_with_hidden_thief((0, 0)),
        "cop",
        "belief_pursuit_evasion",
        np.random.default_rng(17),
        opponent_belief=belief,
    )
    second = _opponent_action(
        state_with_hidden_thief((6, 6)),
        "cop",
        "belief_pursuit_evasion",
        np.random.default_rng(17),
        opponent_belief=belief,
    )

    assert first == second


def test_recurrent_opponent_families_and_local_expert_branches() -> None:
    rng = random.Random(9)
    state = _state(cop=(0, 0), thief=(3, 3))
    assert _initial_state(rng, random_start=False).cop_position == (0, 0)
    assert "STAY" in _legal(state, "cop") and "STAY" in _legal(state, "police")
    assert _opponent_action(state, "cop", "random", rng) in COP_ACTIONS
    assert _opponent_action(state, "cop", "wall", rng) in COP_ACTIONS
    assert _opponent_action(state, "police", "wall", rng) in {"N", "S", "E", "W", "STAY"}
    with pytest.raises(RuntimeError, match="was not loaded"):
        _opponent_action(state, "cop", "historical_checkpoint", rng)

    class Historical:
        barriers_remaining = 0

        def _build_obs(self, *_args, **_kwargs):
            return object()

        def select_action(self, _observation, training=False):
            assert training is False
            return 0, 0.0, 0.0

    # N is illegal from (0, 0), so the historical action is legally masked.
    historical = _opponent_action(
        state, "cop", "historical_checkpoint", rng, historical_policy=Historical()
    )
    assert historical in _legal(state, "cop")

    belief = BeliefEngine(7, "cop")
    probability = np.zeros((7, 7))
    probability[0, 1] = 1.0
    belief._belief = BeliefState(7, probability, confidence=1.0)
    assert _belief_expert_action((0, 0), "cop", belief, COP_ACTIONS) in COP_ACTIONS
    assert _belief_expert_action((0, 0), "police", belief, ["E", "STAY"]) in {"E", "STAY"}
    assert _opponent_action(state, "cop", "belief_pursuit_evasion", rng, opponent_belief=belief)
    assert _opponent_action(
        _state(turn=1), "cop", "local_adversarial_ensemble", rng, opponent_belief=belief
    )
    assert _opponent_action(
        _state(turn=4), "police", "local_adversarial_ensemble", rng, opponent_belief=belief
    )
    with pytest.raises(RuntimeError, match="requires a local Bayesian belief"):
        _opponent_action(state, "cop", "belief_pursuit_evasion", rng)
    with pytest.raises(RuntimeError, match="unknown opponent family"):
        _opponent_action(state, "cop", "unknown", rng, opponent_belief=belief)
