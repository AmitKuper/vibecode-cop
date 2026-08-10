"""Replay buffer."""

from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ReplayItem:
    observation: np.ndarray
    action: int
    reward: float
    next_observation: np.ndarray
    done: bool
    next_mask: np.ndarray


class ReplayBuffer:
    def __init__(self, capacity: int) -> None:
        self.items: deque[ReplayItem] = deque(maxlen=capacity)

    def add(self, item: ReplayItem) -> None:
        self.items.append(item)

    def sample(self, rng: random.Random, count: int) -> list[ReplayItem]:
        return rng.sample(self.items, count)

    def __len__(self) -> int:
        return len(self.items)
