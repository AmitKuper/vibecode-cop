"""Cover LegacyResearchPolicy (feed-forward checkpoint) in policies_scripted."""

from __future__ import annotations

import random

import torch

from cop_worker.belief_engine import BeliefEngine
from cop_worker.rl.action_space import COP_ACTIONS, THIEF_ACTIONS
from cop_worker.rl.networks import PPONet
from cop_worker.rl.research_evaluation import LegacyResearchPolicy
from cop_worker.rl.train_recurrent import _initial_state
from cop_worker.scent import make_scent_fields


def _save_ppo(path, in_channels, n_actions):
    net = PPONet(grid_size=7, n_actions=n_actions, hidden=16, in_channels=in_channels)
    torch.save(
        {
            "net": net.state_dict(),
            "updates": 1,
            "n_actions": n_actions,
            "n_channels": in_channels,
        },
        path,
    )


def test_legacy_thief_policy_acts_legally(tmp_path):
    path = tmp_path / "thief_ppo.pt"
    _save_ppo(path, in_channels=4, n_actions=len(THIEF_ACTIONS))
    policy = LegacyResearchPolicy(path, "thief")
    policy.reset(11)
    state = _initial_state(random.Random(7), random_start=False)
    action = policy.act(state, make_scent_fields(7), BeliefEngine(7, "thief"), random.Random(1), 1)
    assert action in THIEF_ACTIONS


def test_legacy_cop_policy_acts_legally(tmp_path):
    path = tmp_path / "cop_ppo.pt"
    _save_ppo(path, in_channels=5, n_actions=len(COP_ACTIONS))
    policy = LegacyResearchPolicy(path, "cop")
    policy.reset(3)
    # reset restores the barrier budget from the loaded quota.
    assert policy.policy.barriers_remaining == policy.policy.barrier_quota
    state = _initial_state(random.Random(9), random_start=False)
    action = policy.act(state, make_scent_fields(7), BeliefEngine(7, "cop"), random.Random(2), 2)
    assert action in COP_ACTIONS
