"""Evidence-contract tests for recurrent training — episodes, resume, and promotion."""

import random

import pytest
import torch

from cop_worker.rl.action_space import COP_ACTIONS
from cop_worker.rl.local_obs_adapter import obs_tensor_shape
from cop_worker.rl.recurrent_policy import RecurrentActorCritic
from cop_worker.rl.train_recurrent import (
    FAMILIES,
    _collect_demonstrations,
    _initial_state,
    _pretrain_imitation,
    _promotion_comparison,
    _run_episode,
    _wilson,
    train,
)
from tests.helpers_codex_recurrent import _state


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
        "cop_worker.rl.train_recurrent._initial_state",
        lambda *_args, **_kwargs: _state(cop=(0, 0), thief=(1, 0)),
    )
    monkeypatch.setattr("cop_worker.rl.train_recurrent._opponent_action", lambda *_a, **_kw: "STAY")
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
    monkeypatch.setattr(
        "cop_worker.rl.train_recurrent._pretrain_imitation", lambda *_a, **_kw: None
    )

    def fake_episode(network, *_args, **_kwargs):
        scalar = next(network.parameters()).reshape(-1)[0]
        return [(scalar, True, scalar, scalar, scalar, 1.0)], "cop", 1

    monkeypatch.setattr("cop_worker.rl.train_recurrent._run_episode", fake_episode)
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
        "cop_worker.rl.train_recurrent._initial_state",
        lambda *_args, **_kwargs: _state(turn=35),
    )
    trajectory, winner, turns = _run_episode(
        _EastNetwork(), "cop", "random", random.Random(2), False, True
    )
    assert trajectory == [] and winner in {"police", "thief"} and turns == 35

    one_feature = torch.zeros((1, obs_tensor_shape(7)))
    one_label = torch.zeros(1, dtype=torch.long)
    monkeypatch.setattr(
        "cop_worker.rl.train_recurrent._collect_demonstrations",
        lambda *_args, **_kwargs: (one_feature, one_label),
    )
    network = RecurrentActorCritic(obs_tensor_shape(7), len(COP_ACTIONS), 8)
    _pretrain_imitation(network, "cop", random.Random(1), object(), updates=1)
