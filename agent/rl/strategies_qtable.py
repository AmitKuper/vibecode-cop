"""Tabular Q-learning agent for cop and thief."""

from __future__ import annotations

import random
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path

from agent.rl.environment import N_ACTIONS
from agent.rl.strategies_base import _argmax2d, _decode_1hot


def _cop_state(obs: list) -> tuple:
    """Discretise cop obs to (cop_x, cop_y, scent_peak_x, scent_peak_y)."""
    cx, cy = _decode_1hot(obs[0])
    sx, sy = _argmax2d(obs[2])
    return (cx, cy, sx, sy)


def _thief_state(obs: list) -> tuple:
    """Discretise thief obs to (thief_x, thief_y, last_cop_x, last_cop_y)."""
    tx, ty = _decode_1hot(obs[0])
    cx, cy = _decode_1hot(obs[1])
    return (tx, ty, cx, cy)


class QTableAgent:
    """Tabular Q-learning agent with epsilon-greedy exploration.

    Works for both roles; provide the appropriate state_fn at construction time.
    """

    def __init__(
        self,
        role: str,
        n_actions: int = N_ACTIONS,
        lr: float = 0.1,
        gamma: float = 0.95,
        eps_start: float = 1.0,
        eps_end: float = 0.05,
        eps_decay: float = 0.9999,
        state_fn: Callable | None = None,
    ):
        self.role = role
        self.n_actions = n_actions
        self.lr = lr
        self.gamma = gamma
        self.eps = eps_start
        self.eps_end = eps_end
        self.eps_decay = eps_decay
        self._state_fn: Callable = state_fn or (_cop_state if role == "cop" else _thief_state)
        self.q: dict[tuple, list[float]] = defaultdict(lambda: [0.0] * n_actions)

    def _state(self, obs: list) -> tuple:
        return self._state_fn(obs)

    def select_action(self, obs: list, training: bool = False) -> int:
        if training and random.random() < self.eps:
            return random.randrange(self.n_actions)
        s = self._state(obs)
        return int(max(range(self.n_actions), key=lambda a: self.q[s][a]))

    def update(self, obs: list, action: int, reward: float, next_obs: list, done: bool) -> None:
        s = self._state(obs)
        ns = self._state(next_obs)
        td_target = reward + (0.0 if done else self.gamma * max(self.q[ns]))
        self.q[s][action] += self.lr * (td_target - self.q[s][action])
        if self.eps > self.eps_end:
            self.eps *= self.eps_decay

    def save(self, path: Path) -> None:
        import json

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {"role": self.role, "eps": self.eps, "q": {str(k): v for k, v in self.q.items()}}
        path.write_text(json.dumps(data))

    @classmethod
    def load(cls, path: Path, role: str) -> QTableAgent:
        import json

        data = json.loads(Path(path).read_text())
        agent = cls(role)
        agent.eps = data.get("eps", agent.eps_end)
        for k_str, v in data.get("q", {}).items():
            k = tuple(int(x) for x in k_str.strip("()").split(", "))
            agent.q[k] = v
        return agent
