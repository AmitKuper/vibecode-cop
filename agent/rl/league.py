"""Fixed-opponent and league (pool) PPO training built on a shared rollout loop."""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from pathlib import Path

from agent.rl.config import RLGameConfig
from agent.rl.environment import CopThiefEnv
from agent.rl.ppo import PPOAgent

logger = logging.getLogger(__name__)


def _frozen_action(opponent, obs: list) -> int:
    """Return an action from a frozen (non-updating) opponent (DQN or PPO)."""
    result = opponent.select_action(obs, training=False)
    return result[0] if isinstance(result, tuple) else int(result)


def _run_ppo_opponent_loop(
    role: str,
    agent: PPOAgent,
    env: CopThiefEnv,
    total_steps: int,
    rollout_size: int,
    log_interval: int,
    best_path: Path,
    log_tag: str,
    opponent_sampler: Callable,
) -> PPOAgent:
    """Shared rollout-and-update loop for fixed-opponent and league PPO training."""
    winners: list = []
    ep_lens: list = []
    step = update_count = 0
    best_wr = -1.0
    t0 = time.time()
    cop_obs, thief_obs = env.reset()
    current_opp = opponent_sampler()
    done = False
    info: dict = {}

    while step < total_steps:
        for _ in range(rollout_size):
            agent_obs = cop_obs if role == "cop" else thief_obs
            opp_obs = thief_obs if role == "cop" else cop_obs
            agent_act, lp, val = agent.select_action(agent_obs)
            opp_act = _frozen_action(current_opp, opp_obs)
            cop_act = agent_act if role == "cop" else opp_act
            thief_act = opp_act if role == "cop" else agent_act
            next_cop, next_thief, cop_r, thief_r, done, info = env.step(cop_act, thief_act)
            agent_r = cop_r if role == "cop" else thief_r
            agent.push(agent_obs, agent_act, lp, agent_r, val, done)
            cop_obs, thief_obs = next_cop, next_thief
            step += 1
            if done:
                winners.append(info.get("winner"))
                ep_lens.append(info.get("turn", 0))
                cop_obs, thief_obs = env.reset()
                current_opp = opponent_sampler()
                done = False
        agent_obs = cop_obs if role == "cop" else thief_obs
        agent.update(agent_obs, done)
        update_count += 1
        if update_count % log_interval == 0 and winners:
            window = winners[-100:]
            wr = window.count(role) / len(window)
            avg_len = sum(ep_lens[-100:]) / len(ep_lens[-100:])
            elapsed = time.time() - t0
            logger.info(
                f"[{log_tag}] step={step:>7}  {role}_wr={wr:.2f}"
                f"  avg_len={avg_len:.1f}  updates={update_count}  elapsed={elapsed:.0f}s"
            )
            if wr > best_wr:
                best_wr = wr
                agent.save(best_path)

    logger.info(f"[{log_tag}] Done. Best {role}_wr={best_wr:.2f} → {best_path}")
    agent.load(best_path)
    return agent


def train_ppo_vs_frozen(
    role: str,
    frozen_opponent,
    config: RLGameConfig | None = None,
    total_steps: int = 400_000,
    rollout_size: int = 512,
    log_interval: int = 20,
    models_dir: Path = Path("models"),
    net_type: str = "mlp",
    hidden: int = 128,
    tag: str = "",
) -> PPOAgent:
    """Train a PPO ``role`` agent against a single frozen opponent.

    ``tag`` is appended to filenames.
    """
    cfg = config or RLGameConfig()
    env = CopThiefEnv(cfg)
    n_actions = env.n_cop_actions if role == "cop" else env.n_thief_actions
    n_channels = env.n_cop_channels if role == "cop" else env.n_thief_channels
    agent = PPOAgent(
        role,
        grid_size=cfg.grid_size,
        rollout_size=rollout_size,
        net_type=net_type,
        hidden=hidden,
        n_actions=n_actions,
        n_channels=n_channels,
    )
    suffix = f"_{tag}" if tag else ""
    best_path = models_dir / f"{role}_ppo_frozen{suffix}_best.pt"
    models_dir.mkdir(parents=True, exist_ok=True)
    agent = _run_ppo_opponent_loop(
        role=role,
        agent=agent,
        env=env,
        total_steps=total_steps,
        rollout_size=rollout_size,
        log_interval=log_interval,
        best_path=best_path,
        log_tag=f"PPO-frozen {role}",
        opponent_sampler=lambda: frozen_opponent,
    )
    agent.save(models_dir / f"{role}_ppo_frozen{suffix}.pt")
    return agent


def train_ppo_league(
    role: str,
    opponent_pool: list,
    opponent_weights: list[float] | None = None,
    config: RLGameConfig | None = None,
    total_steps: int = 500_000,
    rollout_size: int = 512,
    log_interval: int = 20,
    models_dir: Path = Path("models"),
    net_type: str = "mlp",
    hidden: int = 128,
    tag: str = "league",
) -> PPOAgent:
    """Train a PPO role agent against a weighted pool of frozen opponents."""
    cfg = config or RLGameConfig()
    env = CopThiefEnv(cfg)
    n_actions = env.n_cop_actions if role == "cop" else env.n_thief_actions
    n_channels = env.n_cop_channels if role == "cop" else env.n_thief_channels
    agent = PPOAgent(
        role,
        grid_size=cfg.grid_size,
        rollout_size=rollout_size,
        net_type=net_type,
        hidden=hidden,
        n_actions=n_actions,
        n_channels=n_channels,
    )
    weights = opponent_weights or [1.0] * len(opponent_pool)
    norm_weights = [w / sum(weights) for w in weights]

    def _sample_opponent():
        return random.choices(opponent_pool, weights=norm_weights)[0]

    best_path = models_dir / f"{role}_ppo_{tag}_best.pt"
    models_dir.mkdir(parents=True, exist_ok=True)
    agent = _run_ppo_opponent_loop(
        role=role,
        agent=agent,
        env=env,
        total_steps=total_steps,
        rollout_size=rollout_size,
        log_interval=log_interval,
        best_path=best_path,
        log_tag=f"PPO-league {role}",
        opponent_sampler=_sample_opponent,
    )
    agent.save(models_dir / f"{role}_ppo_{tag}.pt")
    return agent
