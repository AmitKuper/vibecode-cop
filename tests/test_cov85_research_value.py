"""Behavioral tests for cop_worker.rl.research_value_training (tiny nets, no GPU)."""

from __future__ import annotations

import random

import numpy as np
import pytest
import torch

from cop_worker.belief_engine import BeliefEngine
from cop_worker.rl.action_space import COP_ACTIONS, THIEF_ACTIONS
from cop_worker.rl.recurrent_policy import RecurrentActorCritic
from cop_worker.rl.research_value_training import (
    DuelingDoubleQNetwork,
    ReplayItem,
    _ddqn_update,
    _frozen_opponent,
    _masked_epsilon_action,
    load_dqn_policy,
    train_ddqn,
    train_q_table,
)
from cop_worker.rl.train_recurrent import _initial_state

INPUT = 4 * 7 * 7 + 5


def _recurrent_ckpt(tmp_path, role):
    n = len(COP_ACTIONS if role == "cop" else THIEF_ACTIONS)
    net = RecurrentActorCritic(INPUT, n, 8)
    path = tmp_path / f"{role}_recurrent.pt"
    payload = {
        "role": role,
        "algorithm": "RecurrentA2C-GRU",
        "input_size": INPUT,
        "n_actions": n,
        "hidden_size": 8,
        "training_steps": 1,
        "state_dict": net.state_dict(),
    }
    torch.save(payload, path)
    return path


def test_train_q_table_produces_policy_and_artifact(tmp_path):
    incumbent = _recurrent_ckpt(tmp_path, "thief")
    output = tmp_path / "q.json"
    policy, metrics = train_q_table(
        "cop", episodes=2, seed=7, incumbent_path=incumbent, output=output
    )
    assert output.exists() and metrics["algorithm"] == "TabularQ"
    assert metrics["states"] > 0
    state = _initial_state(random.Random(3), random_start=False)
    action = policy.act(state, None, BeliefEngine(7, "cop"), random.Random(1), 1)
    assert action in COP_ACTIONS
    policy.reset(0)


def test_train_ddqn_and_load_roundtrip(tmp_path):
    incumbent = _recurrent_ckpt(tmp_path, "cop")
    output = tmp_path / "ddqn.pt"
    policy, metrics = train_ddqn(
        "thief", episodes=1, seed=11, incumbent_path=incumbent, output=output, hidden_size=16
    )
    assert output.exists() and metrics["algorithm"] == "DuelingDoubleDQN"
    assert metrics["environment_steps"] > 0
    loaded = load_dqn_policy(output, "thief")
    state = _initial_state(random.Random(5), random_start=False)
    from cop_worker.scent import make_scent_fields

    action = loaded.act(state, make_scent_fields(7), BeliefEngine(7, "thief"), random.Random(1), 2)
    assert action in THIEF_ACTIONS
    loaded.reset(0)


def test_load_dqn_policy_rejects_bad_artifacts(tmp_path):
    recurrent = _recurrent_ckpt(tmp_path, "thief")
    with pytest.raises(ValueError, match="not a DuelingDoubleDQN artifact"):
        load_dqn_policy(recurrent, "thief")
    ddqn_path = tmp_path / "cop_ddqn.pt"
    net = DuelingDoubleQNetwork(INPUT, len(COP_ACTIONS), 16)
    payload = {
        "role": "cop",
        "algorithm": "DuelingDoubleDQN",
        "input_size": INPUT,
        "n_actions": len(COP_ACTIONS),
        "hidden_size": 16,
        "state_dict": net.state_dict(),
    }
    torch.save(payload, ddqn_path)
    with pytest.raises(ValueError, match="not a thief artifact"):
        load_dqn_policy(ddqn_path, "thief")
    assert load_dqn_policy(ddqn_path, "cop").role == "cop"


def test_frozen_opponent_selects_family(tmp_path):
    ddqn_path = tmp_path / "thief_ddqn.pt"
    net = DuelingDoubleQNetwork(INPUT, len(THIEF_ACTIONS), 16)
    payload = {
        "role": "thief",
        "algorithm": "DuelingDoubleDQN",
        "input_size": INPUT,
        "n_actions": len(THIEF_ACTIONS),
        "hidden_size": 16,
        "state_dict": net.state_dict(),
    }
    torch.save(payload, ddqn_path)
    assert _frozen_opponent("cop", "historical_checkpoint", ddqn_path).role == "thief"
    recurrent = _recurrent_ckpt(tmp_path, "cop")
    assert _frozen_opponent("thief", "historical_checkpoint", recurrent).role == "cop"
    scripted = _frozen_opponent("cop", "anti_loop", ddqn_path)
    assert scripted.role == "thief" and scripted.family == "anti_loop"


def test_masked_epsilon_action_explore_and_exploit():
    torch.manual_seed(0)
    net = DuelingDoubleQNetwork(INPUT, len(THIEF_ACTIONS), 16)
    features = torch.zeros(INPUT)
    mask = torch.tensor([True, True, False, False, True])
    rng = random.Random(4)
    for _ in range(5):
        assert _masked_epsilon_action(net, features, mask, 1.0, rng) in (0, 1, 4)
    greedy = _masked_epsilon_action(net, features, mask, 0.0, rng)
    assert greedy in (0, 1, 4)


def test_ddqn_update_returns_loss():
    torch.manual_seed(1)
    online = DuelingDoubleQNetwork(INPUT, len(THIEF_ACTIONS), 16)
    target = DuelingDoubleQNetwork(INPUT, len(THIEF_ACTIONS), 16)
    optimizer = torch.optim.Adam(online.parameters(), lr=1e-3)
    obs = np.zeros(INPUT, dtype=np.float32)
    mask = np.array([True] * 5)
    batch = [
        ReplayItem(obs, 0, 1.0, obs, False, mask),
        ReplayItem(obs, 1, -1.0, obs, True, mask),
        ReplayItem(obs, 2, 0.1, obs, False, mask),
    ]
    loss = _ddqn_update(online, target, optimizer, batch, gamma=0.99)
    assert isinstance(loss, float) and loss >= 0.0
