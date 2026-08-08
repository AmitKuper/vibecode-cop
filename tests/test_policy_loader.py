"""Fast unit tests for checkpoint loading / network reconstruction.

Builds tiny in-memory checkpoints and loads them — no real model files, no
network, no training.
"""

from __future__ import annotations

import torch

from cop_worker.rl.networks import DQNNet, PPONet
from cop_worker.rl.policy import RLPolicy
from cop_worker.rl.policy_loader import load_checkpoint, rebuild_net


def _save_ppo(path, in_channels=4, n_actions=5):
    net = PPONet(grid_size=7, n_actions=n_actions, hidden=16, in_channels=in_channels)
    torch.save(
        {"net": net.state_dict(), "updates": 1, "n_actions": n_actions, "n_channels": in_channels},
        path,
    )


def _save_dqn(path, in_channels=4, n_actions=5):
    net = DQNNet(grid_size=7, n_actions=n_actions, hidden=16, in_channels=in_channels)
    torch.save(
        {"net": net.state_dict(), "n_actions": n_actions, "n_channels": in_channels}, path
    )


def test_load_ppo_thief_checkpoint(tmp_path):
    p = tmp_path / "thief_ppo.pt"
    _save_ppo(p)
    policy = load_checkpoint(p, "thief", max_steps=35)
    assert isinstance(policy, RLPolicy)
    assert policy.algo == "ppo" and policy.role == "thief"


def test_load_dqn_thief_checkpoint(tmp_path):
    p = tmp_path / "thief_dqn.pt"
    _save_dqn(p)
    policy = load_checkpoint(p, "thief", max_steps=35)
    assert policy.algo == "dqn"


def test_load_cop_five_channel_infers_barrier_quota(tmp_path):
    # 5-channel cop model → loader infers a positive barrier quota from config.
    p = tmp_path / "cop_ppo.pt"
    _save_ppo(p, in_channels=5, n_actions=9)
    policy = load_checkpoint(p, "cop", max_steps=35)
    assert policy.role == "cop"
    assert policy.barrier_quota > 0


def test_rebuild_net_infers_mlp_architecture():
    net = PPONet(grid_size=7, n_actions=5, hidden=16, in_channels=4)
    ckpt = {"n_actions": 5, "n_channels": 4}
    rebuilt = rebuild_net(net.state_dict(), ckpt, "ppo", torch.device("cpu"))
    rebuilt.load_state_dict(net.state_dict())  # shapes must line up
    logits, value = rebuilt(torch.randn(1, 4, 7, 7))
    assert logits.shape == (1, 5) and value.shape == (1, 1)
