"""Cover architecture-inference branches and channel validation in policy_loader."""

from __future__ import annotations

import pytest
import torch

from cop_worker.rl.networks import DQNNet, PPONet
from cop_worker.rl.observation import observation_shape
from cop_worker.rl.policy_loader import load_checkpoint, rebuild_net


def test_rebuild_net_infers_cnn_channels_and_actions():
    net = DQNNet(grid_size=7, n_actions=5, in_channels=4, net_type="cnn")
    # Empty ckpt forces inference of grid_size, n_channels, and n_actions.
    rebuilt = rebuild_net(net.state_dict(), {}, "dqn", torch.device("cpu"))
    rebuilt.load_state_dict(net.state_dict())
    q = rebuilt(torch.randn(1, 4, 7, 7))
    assert q.shape == (1, 5)


def test_rebuild_net_infers_mlp_channels_from_flat_input():
    net = PPONet(grid_size=7, n_actions=5, in_channels=4, net_type="mlp")
    rebuilt = rebuild_net(net.state_dict(), {}, "ppo", torch.device("cpu"))
    rebuilt.load_state_dict(net.state_dict())
    logits, value = rebuilt(torch.randn(1, 4, 7, 7))
    assert logits.shape == (1, 5) and value.shape == (1, 1)


def test_load_checkpoint_rejects_channel_mismatch(tmp_path):
    expected = observation_shape(7, "thief", 0)[0]
    wrong = expected + 1
    net = PPONet(grid_size=7, n_actions=5, in_channels=wrong)
    path = tmp_path / "thief_bad.pt"
    torch.save({"net": net.state_dict(), "updates": 1, "n_channels": wrong}, path)
    with pytest.raises(ValueError, match="channel mismatch"):
        load_checkpoint(path, "thief", max_steps=35)
