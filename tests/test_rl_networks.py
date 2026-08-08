"""Fast unit tests for DQN / PPO network architectures.

Tiny forward passes on CPU — no training, no LLM, no disk.
"""

from __future__ import annotations

import torch

from cop_worker.rl.networks import DQNNet, PPONet

N = 7
C = 4


def _obs(batch=2):
    torch.manual_seed(0)
    return torch.randn(batch, C, N, N)


def test_dqn_forward_shape_mlp():
    net = DQNNet(grid_size=N, n_actions=5, hidden=32, net_type="mlp", in_channels=C)
    out = net(_obs())
    assert out.shape == (2, 5)


def test_dqn_forward_shape_cnn():
    net = DQNNet(grid_size=N, n_actions=9, hidden=16, net_type="cnn", in_channels=C)
    out = net(_obs(batch=1))
    assert out.shape == (1, 9)


def test_ppo_forward_returns_logits_and_value():
    net = PPONet(grid_size=N, n_actions=5, hidden=32, net_type="mlp", in_channels=C)
    logits, value = net(_obs())
    assert logits.shape == (2, 5)
    assert value.shape == (2, 1)


def test_ppo_get_action_deterministic_is_argmax():
    net = PPONet(grid_size=N, n_actions=5, hidden=32, net_type="mlp", in_channels=C)
    obs = _obs(batch=1)
    logits, _ = net(obs)
    action, log_prob, entropy, value = net.get_action(obs, deterministic=True)
    assert int(action.item()) == int(logits.argmax(dim=-1).item())
    assert log_prob.shape == (1,) and entropy.shape == (1,) and value.shape == (1, 1)


def test_ppo_get_action_sampled_is_legal_index():
    net = PPONet(grid_size=N, n_actions=5, hidden=32, net_type="mlp", in_channels=C)
    torch.manual_seed(3)
    action, _, _, _ = net.get_action(_obs(batch=1), deterministic=False)
    assert 0 <= int(action.item()) < 5
