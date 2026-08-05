"""Evidence-contract tests for recurrent held-out tournaments."""

from unittest.mock import patch

import numpy as np

from agent.belief_engine import BeliefEngine
from agent.domain.types import DomainState
from agent.observation import BeliefState
from agent.rl.train_recurrent import FAMILIES, _opponent_action, evaluate


def test_evaluation_uses_exact_six_gamelet_series_and_official_scores():
    calls = []

    def fake_episode(*args, **kwargs):
        calls.append((args, kwargs))
        return [], "cop", 7

    with patch("agent.rl.train_recurrent._run_episode", side_effect=fake_episode):
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
