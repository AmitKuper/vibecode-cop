"""Rollout buffer dataclass for PPO experience collection."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Rollout:
    """Fixed-size rollout storage for PPO updates.

    Stores one window of (obs, action, log_prob, reward, value, done) tuples
    collected during environment interaction. Cleared after each PPO update.
    """

    obs: list = field(default_factory=list)
    actions: list = field(default_factory=list)
    log_probs: list = field(default_factory=list)
    rewards: list = field(default_factory=list)
    values: list = field(default_factory=list)
    dones: list = field(default_factory=list)

    def push(self, obs, action, log_prob, reward, value, done):
        self.obs.append(obs)
        self.actions.append(action)
        self.log_probs.append(log_prob)
        self.rewards.append(reward)
        self.values.append(value)
        self.dones.append(done)

    def clear(self):
        self.obs.clear()
        self.actions.clear()
        self.log_probs.clear()
        self.rewards.clear()
        self.values.clear()
        self.dones.clear()

    def __len__(self):
        return len(self.obs)


# Backward-compatible alias used inside ppo.py
_Rollout = Rollout
