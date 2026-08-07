"""Evidence-contract tests for recurrent training and held-out tournaments."""

import random
import sys
from unittest.mock import patch

import numpy as np
import pytest
import torch

from cop_worker.belief_engine import BeliefEngine
from cop_worker.domain.types import DomainState
from cop_worker.observation import BeliefState
from cop_worker.rl.action_space import COP_ACTIONS
from cop_worker.rl.local_obs_adapter import obs_tensor_shape
from cop_worker.rl.recurrent_policy import RecurrentActorCritic
from cop_worker.rl.train_recurrent import (
    FAMILIES,
    _belief_expert_action,
    _collect_demonstrations,
    _initial_state,
    _legal,
    _opponent_action,
    _pretrain_imitation,
    _promotion_comparison,
    _run_episode,
    _wilson,
    evaluate,
    train,
)


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


def _state(*, turn: int = 0, cop=(0, 0), thief=(2, 2)) -> DomainState:
    return DomainState(
        turn=turn,
        grid_size=7,
        cop_position=cop,
        thief_position=thief,
        barriers=[],
        cop_barriers_remaining=14,
        move_history=[],
        scent_grid=[[0.0] * 7 for _ in range(7)],
    )


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


class _EastNetwork(torch.nn.Module):
    def forward(self, features, hidden):
        logits = torch.zeros((features.shape[0], len(COP_ACTIONS)))
        logits[:, COP_ACTIONS.index("E")] = 20.0
        return logits, torch.zeros(features.shape[0]), hidden


@pytest.mark.parametrize(
    ("training", "temperature", "force_expert"),
    [(True, None, False), (False, 0.5, False), (False, None, True)],
)
def test_episode_actor_modes_finish_via_canonical_transition(
    monkeypatch, training, temperature, force_expert
) -> None:
    monkeypatch.setattr(
        "agent.rl.train_recurrent._initial_state",
        lambda *_args, **_kwargs: _state(cop=(0, 0), thief=(1, 0)),
    )
    monkeypatch.setattr("agent.rl.train_recurrent._opponent_action", lambda *_a, **_kw: "STAY")
    latency = []
    trajectory, winner, turns = _run_episode(
        _EastNetwork(),
        "cop",
        "random",
        random.Random(3),
        training=training,
        random_start=True,
        expert_probability=1.0,
        evaluation_temperature=temperature,
        force_expert_actor=force_expert,
        latency_samples=latency,
    )
    assert trajectory and winner == "cop" and turns in {1, 2}
    assert bool(latency) is (not force_expert)


def test_training_resume_schedules_and_promotion_contract(monkeypatch) -> None:
    monkeypatch.setattr("agent.rl.train_recurrent._pretrain_imitation", lambda *_a, **_kw: None)

    def fake_episode(network, *_args, **_kwargs):
        scalar = next(network.parameters()).reshape(-1)[0]
        return [(scalar, True, scalar, scalar, scalar, 1.0)], "cop", 1

    monkeypatch.setattr("agent.rl.train_recurrent._run_episode", fake_episode)
    cop_network = train("cop", 1, 5, 8, object())
    thief_network = train("police", 1, 6, 8, object())
    checkpoint = {
        "role": "cop",
        "input_size": obs_tensor_shape(7),
        "n_actions": len(COP_ACTIONS),
        "hidden_size": 8,
        "state_dict": cop_network.state_dict(),
    }
    resumed = train(
        "cop",
        1,
        7,
        8,
        object(),
        resume_checkpoint=checkpoint,
        resume_expert_probability=0.2,
        resume_imitation_weight=0.3,
    )
    assert not cop_network.training and not thief_network.training and not resumed.training
    with pytest.raises(RuntimeError, match="role does not match"):
        train("police", 0, 8, 8, object(), resume_checkpoint=checkpoint)

    assert _wilson(0, 0) == [0.0, 0.0]
    series = [{"role_score": 10} for _ in range(2)]
    candidate = {
        "families": {family: {"series_results": series, "win_rate": 1.0} for family in FAMILIES},
        "inference_latency_ms": {"p99": 1.0},
        "technical_failures": 0,
        "official_role_score": 100,
    }
    baseline = {
        "families": {
            family: {"series_results": [{"role_score": 0} for _ in range(2)]} for family in FAMILIES
        },
        "official_role_score": 0,
    }
    assert _promotion_comparison(candidate, baseline, 2)["passed"] is True
    candidate["inference_latency_ms"]["p99"] = None
    assert _promotion_comparison(candidate, baseline, 2)["passed"] is False


def test_random_start_collision_demonstrations_and_empty_episode(monkeypatch) -> None:
    class CollisionRng:
        values = iter((0, 0, 0, 0, 1, 1))

        def randrange(self, _limit):
            return next(self.values)

    assert _initial_state(CollisionRng()).thief_position == (1, 1)
    features, labels = _collect_demonstrations("cop", random.Random(11), 1, object())
    assert len(features) == len(labels) > 0

    monkeypatch.setattr(
        "agent.rl.train_recurrent._initial_state",
        lambda *_args, **_kwargs: _state(turn=35),
    )
    trajectory, winner, turns = _run_episode(
        _EastNetwork(), "cop", "random", random.Random(2), False, True
    )
    assert trajectory == [] and winner == "police" and turns == 35

    one_feature = torch.zeros((1, obs_tensor_shape(7)))
    one_label = torch.zeros(1, dtype=torch.long)
    monkeypatch.setattr(
        "agent.rl.train_recurrent._collect_demonstrations",
        lambda *_args, **_kwargs: (one_feature, one_label),
    )
    network = RecurrentActorCritic(obs_tensor_shape(7), len(COP_ACTIONS), 8)
    _pretrain_imitation(network, "cop", random.Random(1), object(), updates=1)


def test_evaluation_thief_scoring_and_cli_modes(monkeypatch, tmp_path) -> None:
    with patch("agent.rl.train_recurrent._run_episode", return_value=([], "police", 3)):
        thief_result = evaluate(object(), "police", 1, 3, object(), inference_temperature=0.5)
    assert thief_result["official_role_score"] == len(FAMILIES) * 6 * 10
    assert thief_result["inference_mode"] == "low_temp"

    import cop_worker.rl.train_recurrent as training_module

    historical = tmp_path / "historical.pt"
    historical.write_bytes(b"historical")
    artifact = tmp_path / "cop_recurrent_champion.pt"
    network = RecurrentActorCritic(obs_tensor_shape(7), len(COP_ACTIONS), 8)
    torch.save(
        {
            "role": "cop",
            "input_size": obs_tensor_shape(7),
            "n_actions": len(COP_ACTIONS),
            "hidden_size": 8,
            "training_steps": 35,
            "state_dict": network.state_dict(),
        },
        artifact,
    )
    evidence = tmp_path / "evidence"
    models = tmp_path / "models"
    monkeypatch.setattr("agent.rl.policy_loader.load_checkpoint", lambda *_a, **_kw: object())
    monkeypatch.setattr(training_module, "evaluate", lambda *_a, **_kw: {})
    monkeypatch.setattr(
        training_module, "_promotion_comparison", lambda *_a, **_kw: {"passed": True}
    )

    def invoke(*extra: str) -> None:
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "train_recurrent",
                "--role",
                "cop",
                "--historical-checkpoint",
                str(historical),
                "--models-dir",
                str(models),
                "--evidence-dir",
                str(evidence),
                *extra,
            ],
        )
        training_module.main()

    invoke("--evaluate-only-artifact", str(artifact))
    assert (evidence / "cop_held_out_tournament.json").is_file()
    with pytest.raises(RuntimeError, match="temperature"):
        invoke("--evaluate-only-artifact", str(artifact), "--inference-temperature", "2")

    monkeypatch.setattr(training_module, "train", lambda *_a, **_kw: network)
    invoke("--episodes", "0", "--hidden-size", "8")
    invoke(
        "--episodes",
        "0",
        "--hidden-size",
        "8",
        "--resume-artifact",
        str(artifact),
    )
