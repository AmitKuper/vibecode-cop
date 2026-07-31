"""Combination strategies and Q-table self-play training."""

from __future__ import annotations

from pathlib import Path

from agent.rl.strategies_base import (
    GreedyCopStrategy,
    GreedyThiefStrategy,
    _chebyshev,
    _decode_1hot,
)
from agent.rl.strategies_qtable import QTableAgent


class ComboCopStrategy:
    """Use Greedy-Scent when peak scent is strong; fall back to RL when scent is weak."""

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
    """Use RL when cop is close (danger zone); Greedy-Distance otherwise."""

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
    """Train cop and thief Q-table agents via simultaneous self-play."""
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
