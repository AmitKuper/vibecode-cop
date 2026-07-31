"""DQN and PPO self-play training loops."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from pathlib import Path

from agent.rl.config import RLGameConfig
from agent.rl.dqn import DQNAgent
from agent.rl.environment import CopThiefEnv
from agent.rl.ppo import PPOAgent

logger = logging.getLogger(__name__)


def train_dqn(
    config: RLGameConfig | None = None,
    n_episodes: int = 30_000,
    log_interval: int = 500,
    models_dir: Path = Path("models"),
    net_type: str = "mlp",
    hidden: int = 128,
) -> tuple[DQNAgent, DQNAgent, dict]:
    """Train cop and thief DQN agents via self-play. Returns (cop, thief, metrics)."""
    cfg = config or RLGameConfig()
    env = CopThiefEnv(cfg)
    cop = DQNAgent("cop", grid_size=cfg.grid_size, net_type=net_type, hidden=hidden)
    thief = DQNAgent("thief", grid_size=cfg.grid_size, net_type=net_type, hidden=hidden)

    metrics: dict = defaultdict(list)
    best_cop_wr = best_thief_wr = -1.0
    t0 = time.time()
    models_dir.mkdir(parents=True, exist_ok=True)

    for ep in range(1, n_episodes + 1):
        cop_obs, thief_obs = env.reset()
        done = False
        ep_cop_r = ep_thief_r = 0.0
        info: dict = {}

        while not done:
            cop_act = cop.select_action(cop_obs)
            thief_act = thief.select_action(thief_obs)
            next_cop, next_thief, cop_r, thief_r, done, info = env.step(cop_act, thief_act)
            cop.push(cop_obs, cop_act, cop_r, next_cop, done)
            thief.push(thief_obs, thief_act, thief_r, next_thief, done)
            cop.update(); thief.update()
            cop_obs, thief_obs = next_cop, next_thief
            ep_cop_r += cop_r; ep_thief_r += thief_r

        metrics["winner"].append(info.get("winner"))
        metrics["ep_len"].append(info.get("turn", 0))
        metrics["cop_r"].append(ep_cop_r); metrics["thief_r"].append(ep_thief_r)

        if ep % log_interval == 0:
            window = metrics["winner"][-log_interval:]
            cop_wr = window.count("cop") / len(window)
            thief_wr = 1.0 - cop_wr
            avg_len = sum(metrics["ep_len"][-log_interval:]) / log_interval
            logger.info(f"[DQN] ep={ep:>6}  cop_wr={cop_wr:.2f}  avg_len={avg_len:.1f}"
                        f"  eps={cop.eps:.3f}  elapsed={time.time()-t0:.0f}s")
            if cop_wr > best_cop_wr:
                best_cop_wr = cop_wr; cop.save(models_dir / "cop_dqn_best.pt")
            if thief_wr > best_thief_wr:
                best_thief_wr = thief_wr; thief.save(models_dir / "thief_dqn_best.pt")

    cop.save(models_dir / "cop_dqn.pt"); thief.save(models_dir / "thief_dqn.pt")
    logger.info(f"[DQN] Saved. best cop_wr={best_cop_wr:.2f}, best thief_wr={best_thief_wr:.2f}")
    cop.load(models_dir / "cop_dqn_best.pt"); thief.load(models_dir / "thief_dqn_best.pt")
    return cop, thief, dict(metrics)


def train_ppo(
    config: RLGameConfig | None = None,
    total_steps: int = 500_000,
    rollout_size: int = 256,
    log_interval: int = 20,
    models_dir: Path = Path("models"),
    net_type: str = "mlp",
    hidden: int = 128,
) -> tuple[PPOAgent, PPOAgent, dict]:
    """Train cop and thief PPO agents via self-play. Returns (cop, thief, metrics)."""
    cfg = config or RLGameConfig()
    env = CopThiefEnv(cfg)
    cop = PPOAgent("cop", grid_size=cfg.grid_size, rollout_size=rollout_size,
                   net_type=net_type, hidden=hidden,
                   n_actions=env.n_cop_actions, n_channels=env.n_cop_channels)
    thief = PPOAgent("thief", grid_size=cfg.grid_size, rollout_size=rollout_size,
                     net_type=net_type, hidden=hidden,
                     n_actions=env.n_thief_actions, n_channels=env.n_thief_channels)

    cop_obs, thief_obs = env.reset()
    done = False; info: dict = {}
    metrics: dict = defaultdict(list)
    ep_cop_r = ep_thief_r = 0.0
    step = update_count = 0
    best_cop_wr = best_thief_wr = -1.0
    t0 = time.time()
    models_dir.mkdir(parents=True, exist_ok=True)

    while step < total_steps:
        for _ in range(rollout_size):
            cop_act, cop_lp, cop_val = cop.select_action(cop_obs)
            thief_act, thief_lp, thief_val = thief.select_action(thief_obs)
            next_cop, next_thief, cop_r, thief_r, done, info = env.step(cop_act, thief_act)
            cop.push(cop_obs, cop_act, cop_lp, cop_r, cop_val, done)
            thief.push(thief_obs, thief_act, thief_lp, thief_r, thief_val, done)
            cop_obs, thief_obs = next_cop, next_thief
            ep_cop_r += cop_r; ep_thief_r += thief_r; step += 1
            if done:
                metrics["winner"].append(info.get("winner"))
                metrics["ep_len"].append(info.get("turn", 0))
                metrics["cop_r"].append(ep_cop_r); metrics["thief_r"].append(ep_thief_r)
                ep_cop_r = ep_thief_r = 0.0
                cop_obs, thief_obs = env.reset(); done = False

        cop.update(cop_obs, done); thief.update(thief_obs, done)
        update_count += 1

        if update_count % log_interval == 0 and metrics["winner"]:
            window = metrics["winner"][-100:]
            cop_wr = window.count("cop") / len(window); thief_wr = 1.0 - cop_wr
            avg_len = sum(metrics["ep_len"][-100:]) / len(metrics["ep_len"][-100:])
            logger.info(f"[PPO] step={step:>7}  cop_wr={cop_wr:.2f}  avg_len={avg_len:.1f}"
                        f"  updates={update_count}  elapsed={time.time()-t0:.0f}s")
            if cop_wr > best_cop_wr:
                best_cop_wr = cop_wr; cop.save(models_dir / "cop_ppo_best.pt")
            if thief_wr > best_thief_wr:
                best_thief_wr = thief_wr; thief.save(models_dir / "thief_ppo_best.pt")

    cop.save(models_dir / "cop_ppo.pt"); thief.save(models_dir / "thief_ppo.pt")
    logger.info(f"[PPO] Saved. best cop_wr={best_cop_wr:.2f}, best thief_wr={best_thief_wr:.2f}")
    cop.load(models_dir / "cop_ppo_best.pt"); thief.load(models_dir / "thief_ppo_best.pt")
    return cop, thief, dict(metrics)
