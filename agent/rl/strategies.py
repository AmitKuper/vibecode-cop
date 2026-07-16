"""Heuristic and tabular strategies for cop and thief.

All strategies implement the same interface as DQN/PPO agents:
    select_action(obs: list, training: bool = False) -> int | tuple[int, float, float]

Strategies
----------
GreedyCopStrategy   — moves toward the cell with peak scent (channel 2 of cop obs)
GreedyThiefStrategy — moves to maximise Chebyshev distance from last-revealed cop pos
RandomStrategy      — uniform random (baseline)
QTableAgent         — tabular Q-learning; trains in self-play via train_qtable()
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from pathlib import Path
from typing import Callable

from agent.rl.environment import ACTIONS, N_ACTIONS


# ---------------------------------------------------------------------------
# Helpers: decode positions from asymmetric observation channels
# ---------------------------------------------------------------------------

def _argmax2d(grid: list[list[float]]) -> tuple[int, int]:
    """Return (x, y) of the maximum value in a 2-D grid."""
    best_val = -math.inf
    best_x, best_y = 0, 0
    for y, row in enumerate(grid):
        for x, val in enumerate(row):
            if val > best_val:
                best_val = val
                best_x, best_y = x, y
    return best_x, best_y


def _decode_1hot(grid: list[list[float]]) -> tuple[int, int]:
    """Return (x, y) of the single 1-hot cell (highest value wins on ties)."""
    return _argmax2d(grid)


def _chebyshev(ax: int, ay: int, bx: int, by: int) -> int:
    return max(abs(ax - bx), abs(ay - by))


def _legal_from_obs(pos: tuple[int, int], barriers_ch: list[list[float]], grid_size: int) -> list[int]:
    """Return action indices legal from pos given a barrier channel."""
    x, y = pos
    legal = []
    for i, act in enumerate(ACTIONS):
        if act == "STAY":
            legal.append(i)
            continue
        dx, dy = {"NORTH": (0, -1), "SOUTH": (0, 1), "EAST": (1, 0), "WEST": (-1, 0)}[act]
        nx, ny = x + dx, y + dy
        if 0 <= nx < grid_size and 0 <= ny < grid_size and barriers_ch[ny][nx] < 0.5:
            legal.append(i)
    return legal or [ACTIONS.index("STAY")]


# ---------------------------------------------------------------------------
# Random baseline
# ---------------------------------------------------------------------------

class RandomStrategy:
    """Uniform random action selection — used as a baseline."""

    def __init__(self, n_actions: int = N_ACTIONS):
        self.n_actions = n_actions

    def select_action(self, obs: list, training: bool = False) -> int:
        return random.randrange(self.n_actions)


# ---------------------------------------------------------------------------
# Greedy cop: follow peak scent
# ---------------------------------------------------------------------------

class GreedyCopStrategy:
    """Move toward the cell with the highest scent value.

    Cop observation layout (4 channels):
        0  cop position  (1-hot)
        1  barriers
        2  scent field   (float, peak = thief's likely location)
        3  turns remaining
    """

    def select_action(self, obs: list, training: bool = False) -> int:
        cop_ch, barrier_ch, scent_ch = obs[0], obs[1], obs[2]
        grid_size = len(cop_ch)

        cx, cy = _decode_1hot(cop_ch)
        tx, ty = _argmax2d(scent_ch)

        legal = _legal_from_obs((cx, cy), barrier_ch, grid_size)

        # pick action that brings cop closest to scent peak
        best_idx = legal[0]
        best_dist = math.inf
        for i in legal:
            act = ACTIONS[i]
            dx, dy = {"NORTH": (0, -1), "SOUTH": (0, 1), "EAST": (1, 0), "WEST": (-1, 0), "STAY": (0, 0)}[act]
            nx, ny = cx + dx, cy + dy
            d = _chebyshev(nx, ny, tx, ty)
            if d < best_dist:
                best_dist = d
                best_idx = i
        return best_idx


# ---------------------------------------------------------------------------
# Greedy thief: maximise distance from last-revealed cop position
# ---------------------------------------------------------------------------

class GreedyThiefStrategy:
    """Move to maximize Chebyshev distance from the last-revealed cop position.

    Thief observation layout (4 channels):
        0  thief position        (1-hot)
        1  last revealed cop pos (1-hot)
        2  barriers
        3  turns remaining
    """

    def select_action(self, obs: list, training: bool = False) -> int:
        thief_ch, cop_ch, barrier_ch = obs[0], obs[1], obs[2]
        grid_size = len(thief_ch)

        tx, ty = _decode_1hot(thief_ch)
        cx, cy = _decode_1hot(cop_ch)

        legal = _legal_from_obs((tx, ty), barrier_ch, grid_size)

        # pick action that maximises distance from cop
        best_idx = legal[0]
        best_dist = -1
        for i in legal:
            act = ACTIONS[i]
            dx, dy = {"NORTH": (0, -1), "SOUTH": (0, 1), "EAST": (1, 0), "WEST": (-1, 0), "STAY": (0, 0)}[act]
            nx, ny = tx + dx, ty + dy
            d = _chebyshev(nx, ny, cx, cy)
            if d > best_dist:
                best_dist = d
                best_idx = i
        return best_idx


# ---------------------------------------------------------------------------
# Q-table agent (tabular Q-learning)
# ---------------------------------------------------------------------------

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
        data = {
            "role": self.role,
            "eps": self.eps,
            "q": {str(k): v for k, v in self.q.items()},
        }
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


# ---------------------------------------------------------------------------
# Q-table self-play training
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Combination strategies
# ---------------------------------------------------------------------------

class ComboCopStrategy:
    """Cop: use Greedy-Scent when peak scent is strong (thief trail detected),
    fall back to RL when scent is weak (thief has gone cold)."""

    def __init__(self, rl_agent, scent_threshold: float = 0.3):
        self._greedy = GreedyCopStrategy()
        self._rl = rl_agent
        self._thresh = scent_threshold

    def select_action(self, obs: list, training: bool = False) -> int:
        scent_ch = obs[2]
        peak = max(v for row in scent_ch for v in row)
        if peak >= self._thresh:
            return self._greedy.select_action(obs, training)
        return self._rl.select_action(obs, training)


class ComboThiefStrategy:
    """Thief: use RL when cop is close (danger zone), Greedy-Distance otherwise."""

    def __init__(self, rl_agent, danger_distance: int = 2):
        self._greedy = GreedyThiefStrategy()
        self._rl = rl_agent
        self._danger = danger_distance

    def select_action(self, obs: list, training: bool = False) -> int:
        thief_ch, cop_ch = obs[0], obs[1]
        tx, ty = _decode_1hot(thief_ch)
        cx, cy = _decode_1hot(cop_ch)
        dist = _chebyshev(tx, ty, cx, cy)
        if dist <= self._danger:
            return self._rl.select_action(obs, training)
        return self._greedy.select_action(obs, training)


def train_qtable(
    config=None,
    n_episodes: int = 50_000,
    log_interval: int = 2_000,
    models_dir: Path = Path("models"),
) -> tuple[QTableAgent, QTableAgent, dict]:
    """Train cop and thief Q-table agents via simultaneous self-play.

    Returns (cop_agent, thief_agent, metrics).
    """
    from collections import defaultdict as _dd
    from agent.rl.config import RLGameConfig
    from agent.rl.environment import CopThiefEnv

    cfg = config or RLGameConfig()
    env = CopThiefEnv(cfg)
    cop = QTableAgent("cop")
    thief = QTableAgent("thief")

    metrics: dict = _dd(list)
    cop_wins = thief_wins = 0

    for ep in range(1, n_episodes + 1):
        cop_obs, thief_obs = env.reset()
        done = False
        info: dict = {}

        while not done:
            ca = cop.select_action(cop_obs, training=True)
            ta = thief.select_action(thief_obs, training=True)
            next_cop_obs, next_thief_obs, cr, tr, done, info = env.step(ca, ta)
            cop.update(cop_obs, ca, cr, next_cop_obs, done)
            thief.update(thief_obs, ta, tr, next_thief_obs, done)
            cop_obs, thief_obs = next_cop_obs, next_thief_obs

        winner = info.get("winner")
        if winner == "cop":
            cop_wins += 1
        else:
            thief_wins += 1

        if ep % log_interval == 0:
            total = cop_wins + thief_wins if (cop_wins + thief_wins) > 0 else 1
            win_rate = cop_wins / total
            metrics["cop_win_rate"].append(win_rate)
            metrics["ep"].append(ep)
            print(
                f"[qtable] ep={ep:>6}  cop_wr={win_rate:.2%}  "
                f"eps_cop={cop.eps:.3f}  eps_thief={thief.eps:.3f}  "
                f"states_cop={len(cop.q)}  states_thief={len(thief.q)}"
            )
            cop_wins = thief_wins = 0

    models_dir = Path(models_dir)
    cop.save(models_dir / "cop_qtable.json")
    thief.save(models_dir / "thief_qtable.json")
    print(f"[qtable] Saved models to {models_dir}/")
    return cop, thief, dict(metrics)
