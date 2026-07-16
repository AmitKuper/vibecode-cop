"""Circular experience replay buffer for DQN."""

import random
from collections import deque


class ReplayBuffer:
    """Stores (obs, action, reward, next_obs, done) tuples.

    Observations are stored as-is (nested lists from the environment).
    Consumers convert to tensors when sampling.
    """

    def __init__(self, capacity: int = 20_000):
        self._buf: deque = deque(maxlen=capacity)

    def push(
        self,
        obs: list,
        action: int,
        reward: float,
        next_obs: list,
        done: bool,
    ) -> None:
        self._buf.append((obs, action, reward, next_obs, done))

    def sample(self, batch_size: int) -> tuple:
        """Return a random batch as five separate lists."""
        batch = random.sample(self._buf, batch_size)
        obs, actions, rewards, next_obs, dones = zip(*batch, strict=False)
        return list(obs), list(actions), list(rewards), list(next_obs), list(dones)

    def __len__(self) -> int:
        return len(self._buf)
