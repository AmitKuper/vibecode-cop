"""Evidence-contract tests for recurrent held-out tournaments."""

from unittest.mock import patch

from agent.rl.train_recurrent import FAMILIES, evaluate


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
