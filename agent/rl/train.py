"""Self-play training loops for DQN and PPO agents.

Both algorithms use simultaneous self-play: cop and thief improve against
each other at the same time, so each must handle an increasingly capable
opponent — producing robust policies for competitive play.

CLI usage
---------
  # Train DQN for 30k episodes, save to models/
  python -m agent.rl.train --algo dqn --episodes 30000

  # Train PPO for 500k steps
  python -m agent.rl.train --algo ppo --steps 500000

  # Train both and compare
  python -m agent.rl.train --algo both --episodes 30000 --steps 500000

  # Evaluate saved models
  python -m agent.rl.train --eval-only \
      --cop-model models/cop_dqn.pt --thief-model models/thief_dqn.pt --algo dqn
"""

from __future__ import annotations

import argparse
import logging
import time
from collections import defaultdict
from pathlib import Path

from agent.rl.config import RLGameConfig
from agent.rl.dqn import DQNAgent
from agent.rl.environment import CopThiefEnv
from agent.rl.evaluate import compare, evaluate, print_results
from agent.rl.ppo import PPOAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ======================================================================
# DQN self-play
# ======================================================================

def train_dqn(
    config: RLGameConfig | None = None,
    n_episodes: int = 30_000,
    log_interval: int = 500,
    models_dir: Path = Path("models"),
    net_type: str = "mlp",
    hidden: int = 128,
) -> tuple[DQNAgent, DQNAgent, dict]:
    """Train cop and thief DQN agents via self-play.

    Both agents update every step once the replay buffer is warm (≥ batch_size).
    Returns (cop, thief, metrics).
    """
    cfg = config or RLGameConfig()
    env = CopThiefEnv(cfg)
    cop = DQNAgent("cop", grid_size=cfg.grid_size, net_type=net_type, hidden=hidden)
    thief = DQNAgent("thief", grid_size=cfg.grid_size, net_type=net_type, hidden=hidden)

    metrics: dict = defaultdict(list)
    best_cop_wr = -1.0
    best_thief_wr = -1.0
    t0 = time.time()

    models_dir.mkdir(parents=True, exist_ok=True)

    for ep in range(1, n_episodes + 1):
        cop_obs, thief_obs = env.reset()
        done = False
        ep_cop_r = 0.0
        ep_thief_r = 0.0
        info: dict = {}

        while not done:
            cop_act = cop.select_action(cop_obs)
            thief_act = thief.select_action(thief_obs)

            next_cop, next_thief, cop_r, thief_r, done, info = env.step(cop_act, thief_act)

            cop.push(cop_obs, cop_act, cop_r, next_cop, done)
            thief.push(thief_obs, thief_act, thief_r, next_thief, done)

            cop.update()
            thief.update()

            cop_obs = next_cop
            thief_obs = next_thief
            ep_cop_r += cop_r
            ep_thief_r += thief_r

        metrics["winner"].append(info.get("winner"))
        metrics["ep_len"].append(info.get("turn", 0))
        metrics["cop_r"].append(ep_cop_r)
        metrics["thief_r"].append(ep_thief_r)

        if ep % log_interval == 0:
            window = metrics["winner"][-log_interval:]
            cop_wr = window.count("cop") / len(window)
            thief_wr = 1.0 - cop_wr
            avg_len = sum(metrics["ep_len"][-log_interval:]) / log_interval
            elapsed = time.time() - t0
            logger.info(
                f"[DQN] ep={ep:>6}  cop_wr={cop_wr:.2f}  avg_len={avg_len:.1f}"
                f"  eps={cop.eps:.3f}  elapsed={elapsed:.0f}s"
            )
            # Save best checkpoints independently
            if cop_wr > best_cop_wr:
                best_cop_wr = cop_wr
                cop.save(models_dir / "cop_dqn_best.pt")
            if thief_wr > best_thief_wr:
                best_thief_wr = thief_wr
                thief.save(models_dir / "thief_dqn_best.pt")

    cop.save(models_dir / "cop_dqn.pt")
    thief.save(models_dir / "thief_dqn.pt")
    logger.info(
        f"[DQN] Saved final models to {models_dir}/  "
        f"(best cop_wr={best_cop_wr:.2f}, best thief_wr={best_thief_wr:.2f})"
    )

    # Reload best checkpoints for evaluation
    cop.load(models_dir / "cop_dqn_best.pt")
    thief.load(models_dir / "thief_dqn_best.pt")
    return cop, thief, dict(metrics)


# ======================================================================
# PPO self-play
# ======================================================================

def train_ppo(
    config: RLGameConfig | None = None,
    total_steps: int = 500_000,
    rollout_size: int = 256,
    log_interval: int = 20,
    models_dir: Path = Path("models"),
    net_type: str = "mlp",
    hidden: int = 128,
) -> tuple[PPOAgent, PPOAgent, dict]:
    """Train cop and thief PPO agents via self-play.

    Both agents collect experience during the same rollout window, then each
    runs its own PPO update independently. Returns (cop, thief, metrics).
    """
    cfg = config or RLGameConfig()
    env = CopThiefEnv(cfg)
    cop = PPOAgent("cop", grid_size=cfg.grid_size, rollout_size=rollout_size, net_type=net_type, hidden=hidden,  # noqa: E501
                   n_actions=env.n_cop_actions, n_channels=env.n_cop_channels)
    thief = PPOAgent("thief", grid_size=cfg.grid_size, rollout_size=rollout_size, net_type=net_type, hidden=hidden,  # noqa: E501
                     n_actions=env.n_thief_actions, n_channels=env.n_thief_channels)

    cop_obs, thief_obs = env.reset()
    done = False
    info: dict = {}

    metrics: dict = defaultdict(list)
    ep_cop_r = 0.0
    ep_thief_r = 0.0
    step = 0
    update_count = 0
    best_cop_wr = -1.0
    best_thief_wr = -1.0
    t0 = time.time()

    models_dir.mkdir(parents=True, exist_ok=True)

    while step < total_steps:
        # Collect one rollout
        for _ in range(rollout_size):
            cop_act, cop_lp, cop_val = cop.select_action(cop_obs)
            thief_act, thief_lp, thief_val = thief.select_action(thief_obs)

            next_cop, next_thief, cop_r, thief_r, done, info = env.step(cop_act, thief_act)

            cop.push(cop_obs, cop_act, cop_lp, cop_r, cop_val, done)
            thief.push(thief_obs, thief_act, thief_lp, thief_r, thief_val, done)

            cop_obs = next_cop
            thief_obs = next_thief
            ep_cop_r += cop_r
            ep_thief_r += thief_r
            step += 1

            if done:
                metrics["winner"].append(info.get("winner"))
                metrics["ep_len"].append(info.get("turn", 0))
                metrics["cop_r"].append(ep_cop_r)
                metrics["thief_r"].append(ep_thief_r)
                ep_cop_r = 0.0
                ep_thief_r = 0.0
                cop_obs, thief_obs = env.reset()
                done = False

        cop.update(cop_obs, done)
        thief.update(thief_obs, done)
        update_count += 1

        if update_count % log_interval == 0 and metrics["winner"]:
            window = metrics["winner"][-100:]
            cop_wr = window.count("cop") / len(window)
            thief_wr = 1.0 - cop_wr
            avg_len = sum(metrics["ep_len"][-100:]) / len(metrics["ep_len"][-100:])
            elapsed = time.time() - t0
            logger.info(
                f"[PPO] step={step:>7}  cop_wr={cop_wr:.2f}  avg_len={avg_len:.1f}"
                f"  updates={update_count}  elapsed={elapsed:.0f}s"
            )
            # Save best cop and thief checkpoints independently
            if cop_wr > best_cop_wr:
                best_cop_wr = cop_wr
                cop.save(models_dir / "cop_ppo_best.pt")
            if thief_wr > best_thief_wr:
                best_thief_wr = thief_wr
                thief.save(models_dir / "thief_ppo_best.pt")

    cop.save(models_dir / "cop_ppo.pt")
    thief.save(models_dir / "thief_ppo.pt")
    logger.info(
        f"[PPO] Saved final models to {models_dir}/  "
        f"(best cop_wr={best_cop_wr:.2f}, best thief_wr={best_thief_wr:.2f})"
    )

    # Reload best checkpoints for evaluation
    cop.load(models_dir / "cop_ppo_best.pt")
    thief.load(models_dir / "thief_ppo_best.pt")
    return cop, thief, dict(metrics)


# ======================================================================
# Fixed-opponent training
# ======================================================================

def _frozen_action(opponent, obs: list) -> int:
    """Get action from a frozen (non-learning) opponent — works for DQN and PPO."""
    result = opponent.select_action(obs, training=False)
    # PPO returns (action, log_prob, value); DQN returns int
    return result[0] if isinstance(result, tuple) else int(result)


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
    """Train a PPO agent against a weighted pool of frozen opponents (league training).

    At the start of each episode a new opponent is sampled from the pool
    according to ``opponent_weights``.  Mixing past and present checkpoints
    prevents the co-evolutionary collapse that occurs when training against only
    the latest frozen opponent.

    Args:
        role:              'cop' or 'thief'.
        opponent_pool:     List of frozen agents (DQN or PPO).
        opponent_weights:  Sampling weights (default: uniform).
        tag:               Suffix for checkpoint filenames.
    """
    import random as _rng
    cfg = config or RLGameConfig()
    env = CopThiefEnv(cfg)
    n_actions  = env.n_cop_actions  if role == "cop" else env.n_thief_actions
    n_channels = env.n_cop_channels if role == "cop" else env.n_thief_channels
    agent = PPOAgent(role, grid_size=cfg.grid_size, rollout_size=rollout_size,
                     net_type=net_type, hidden=hidden, n_actions=n_actions, n_channels=n_channels)

    weights = opponent_weights or [1.0] * len(opponent_pool)
    total_w = sum(weights)
    norm_weights = [w / total_w for w in weights]

    cop_obs, thief_obs = env.reset()
    current_opp = _rng.choices(opponent_pool, weights=norm_weights)[0]
    done = False
    info: dict = {}

    winners: list = []
    ep_lens: list = []
    step = 0
    update_count = 0
    best_wr = -1.0
    t0 = time.time()

    best_path = models_dir / f"{role}_ppo_{tag}_best.pt"
    models_dir.mkdir(parents=True, exist_ok=True)

    while step < total_steps:
        for _ in range(rollout_size):
            agent_obs = cop_obs if role == "cop" else thief_obs
            opp_obs   = thief_obs if role == "cop" else cop_obs

            agent_act, lp, val = agent.select_action(agent_obs)
            opp_act = _frozen_action(current_opp, opp_obs)

            cop_act   = agent_act if role == "cop" else opp_act
            thief_act = opp_act   if role == "cop" else agent_act

            next_cop, next_thief, cop_r, thief_r, done, info = env.step(cop_act, thief_act)

            agent_r = cop_r if role == "cop" else thief_r
            agent.push(agent_obs, agent_act, lp, agent_r, val, done)

            cop_obs, thief_obs = next_cop, next_thief
            step += 1

            if done:
                winners.append(info.get("winner"))
                ep_lens.append(info.get("turn", 0))
                cop_obs, thief_obs = env.reset()
                # Re-sample opponent for next episode
                current_opp = _rng.choices(opponent_pool, weights=norm_weights)[0]
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
                f"[PPO-league {role}] step={step:>7}  {role}_wr={wr:.2f}"
                f"  avg_len={avg_len:.1f}  updates={update_count}  elapsed={elapsed:.0f}s"
            )
            if wr > best_wr:
                best_wr = wr
                agent.save(best_path)

    agent.save(models_dir / f"{role}_ppo_{tag}.pt")
    logger.info(f"[PPO-league {role}] Done. Best {role}_wr={best_wr:.2f} → {best_path}")
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
    """Train a single PPO agent against a frozen (non-learning) opponent.

    The frozen opponent selects actions but never updates its weights, giving
    the trainee a consistent, strong adversary to specialise against.

    Args:
        role:             'cop' or 'thief' — the agent being trained.
        frozen_opponent:  Any agent with select_action(obs, training) interface.
        tag:              Label appended to checkpoint filenames, e.g. 'v2'.
    """
    cfg = config or RLGameConfig()
    env = CopThiefEnv(cfg)
    n_actions  = env.n_cop_actions  if role == "cop" else env.n_thief_actions
    n_channels = env.n_cop_channels if role == "cop" else env.n_thief_channels
    agent = PPOAgent(role, grid_size=cfg.grid_size, rollout_size=rollout_size,
                     net_type=net_type, hidden=hidden, n_actions=n_actions, n_channels=n_channels)

    cop_obs, thief_obs = env.reset()
    done = False
    info: dict = {}

    winners: list = []
    ep_lens: list = []
    step = 0
    update_count = 0
    best_wr = -1.0
    t0 = time.time()

    suffix = f"_{tag}" if tag else ""
    best_path = models_dir / f"{role}_ppo_frozen{suffix}_best.pt"

    models_dir.mkdir(parents=True, exist_ok=True)

    while step < total_steps:
        for _ in range(rollout_size):
            agent_obs = cop_obs if role == "cop" else thief_obs
            opp_obs   = thief_obs if role == "cop" else cop_obs

            agent_act, lp, val = agent.select_action(agent_obs)
            opp_act = _frozen_action(frozen_opponent, opp_obs)

            cop_act   = agent_act if role == "cop" else opp_act
            thief_act = opp_act   if role == "cop" else agent_act

            next_cop, next_thief, cop_r, thief_r, done, info = env.step(cop_act, thief_act)

            agent_r = cop_r if role == "cop" else thief_r
            agent.push(agent_obs, agent_act, lp, agent_r, val, done)

            cop_obs, thief_obs = next_cop, next_thief
            step += 1

            if done:
                winners.append(info.get("winner"))
                ep_lens.append(info.get("turn", 0))
                cop_obs, thief_obs = env.reset()
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
                f"[PPO-frozen {role}] step={step:>7}  {role}_wr={wr:.2f}"
                f"  avg_len={avg_len:.1f}  updates={update_count}  elapsed={elapsed:.0f}s"
            )
            if wr > best_wr:
                best_wr = wr
                agent.save(best_path)

    agent.save(models_dir / f"{role}_ppo_frozen{suffix}.pt")
    logger.info(f"[PPO-frozen {role}] Done. Best {role}_wr={best_wr:.2f} → {best_path}")

    agent.load(best_path)
    return agent


def train_cross(
    config: RLGameConfig | None = None,
    total_steps: int = 400_000,
    rollout_size: int = 512,
    models_dir: Path = Path("models"),
    net_type: str = "mlp",
    hidden: int = 128,
    cop_checkpoint: Path | None = None,
    thief_checkpoint: Path | None = None,
    eval_games: int = 500,
) -> tuple:
    """Cross-train cop vs frozen best-thief AND thief vs frozen best-cop.

    Loads the strong checkpoints, then trains each role against its frozen
    opponent. Both trainings run sequentially (cop first, then thief).
    Returns (new_cop, new_thief).
    """
    cfg = config or RLGameConfig()
    models_dir = Path(models_dir)

    # Load frozen opponents
    cop_path   = cop_checkpoint   or models_dir / "cop_ppo_best.pt"
    thief_path = thief_checkpoint or models_dir / "thief_ppo_best.pt"

    from agent.rl.policy import RLPolicy
    frozen_cop   = RLPolicy._load_checkpoint(Path(cop_path),   "cop",   max_steps=cfg.max_steps)
    frozen_thief = RLPolicy._load_checkpoint(Path(thief_path), "thief", max_steps=cfg.max_steps)
    logger.info(f"[cross] Loaded frozen cop   from {cop_path}")
    logger.info(f"[cross] Loaded frozen thief from {thief_path}")

    # Train cop against frozen best thief
    logger.info("=== Cross-training: COP vs frozen best THIEF ===")
    new_cop = train_ppo_vs_frozen(
        "cop", frozen_thief, cfg, total_steps, rollout_size,
        models_dir=models_dir, net_type=net_type, hidden=hidden, tag="v2",
    )

    # Train thief against frozen best cop
    logger.info("=== Cross-training: THIEF vs frozen best COP ===")
    new_thief = train_ppo_vs_frozen(
        "thief", frozen_cop, cfg, total_steps, rollout_size,
        models_dir=models_dir, net_type=net_type, hidden=hidden, tag="v2",
    )

    # Evaluate the new pair
    logger.info("=== Evaluating cross-trained models ===")
    r = evaluate(new_cop, new_thief, cfg, eval_games)
    print_results("Cross-trained cop vs cross-trained thief", r)

    # Also compare against the original PPO models
    logger.info("=== Comparing cross-trained vs original PPO ===")
    compare(frozen_cop, frozen_thief, new_cop, new_thief, cfg, eval_games)

    return new_cop, new_thief


# ======================================================================
# CLI
# ======================================================================

def train_iterated(
    config: RLGameConfig | None = None,
    rounds: int = 3,
    steps_per_round: int = 300_000,
    rollout_size: int = 512,
    models_dir: Path = Path("models"),
    net_type: str = "mlp",
    hidden: int = 128,
    eval_games: int = 300,
    cop_checkpoint: Path | None = None,
    thief_checkpoint: Path | None = None,
) -> tuple:
    """Iterated cross-training: alternate freezing best cop/thief for N rounds.

    Round structure:
      1. Train cop against frozen best thief  → save cop_ppo_iter_rN_best.pt
      2. Train thief against frozen new cop   → save thief_ppo_iter_rN_best.pt
      3. Evaluate the new pair and log stats.

    Each round the new winner becomes the frozen opponent for the next round,
    creating an arms-race dynamic that forces both agents to continuously improve.
    """
    cfg = config or RLGameConfig(use_shaped_rewards=True, random_starts=True)
    models_dir = Path(models_dir)
    models_dir.mkdir(parents=True, exist_ok=True)

    # Bootstrap: load existing best models as round-0 opponents
    cop_path   = cop_checkpoint   or models_dir / "cop_ppo_best.pt"
    thief_path = thief_checkpoint or models_dir / "thief_ppo_best.pt"

    from agent.rl.policy import RLPolicy
    frozen_cop   = RLPolicy._load_checkpoint(Path(cop_path),   "cop",   max_steps=cfg.max_steps)
    frozen_thief = RLPolicy._load_checkpoint(Path(thief_path), "thief", max_steps=cfg.max_steps)
    logger.info(f"[iterated] Bootstrapping from {cop_path} and {thief_path}")

    for rnd in range(1, rounds + 1):
        logger.info(f"\n{'='*60}\n  ITERATED ROUND {rnd}/{rounds}\n{'='*60}")

        cop_tag  = f"iter_r{rnd}"
        thief_tag = f"iter_r{rnd}"

        # Train cop against frozen thief
        logger.info(f"[round {rnd}] Training COP vs frozen thief ...")
        new_cop = train_ppo_vs_frozen(
            "cop", frozen_thief, cfg, steps_per_round, rollout_size,
            models_dir=models_dir, net_type=net_type, hidden=hidden, tag=cop_tag,
        )

        # Train thief against the freshly trained cop (frozen)
        logger.info(f"[round {rnd}] Training THIEF vs new frozen cop ...")
        new_thief = train_ppo_vs_frozen(
            "thief", new_cop, cfg, steps_per_round, rollout_size,
            models_dir=models_dir, net_type=net_type, hidden=hidden, tag=thief_tag,
        )

        # Evaluate on fixed-start env (not shaped) for fair comparison
        eval_cfg = RLGameConfig()
        r = evaluate(new_cop, new_thief, eval_cfg, eval_games)
        print_results(f"Round {rnd} evaluation (cop_iter vs thief_iter)", r)

        # Winners become the frozen opponents for the next round
        frozen_cop   = new_cop
        frozen_thief = new_thief

    logger.info("[iterated] All rounds complete.")
    return frozen_cop, frozen_thief


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Train / evaluate cop-and-thief RL agents")
    p.add_argument("--algo", choices=["dqn", "ppo", "both"], default="ppo",
                   help="Algorithm(s) to train")
    p.add_argument("--mode", choices=["selfplay", "cross", "iterated", "league"], default="selfplay",  # noqa: E501
                   help="selfplay | cross | iterated | league (train vs pool of checkpoints)")
    p.add_argument("--episodes", type=int, default=30_000,
                   help="DQN: number of training episodes")
    p.add_argument("--steps", type=int, default=500_000,
                   help="PPO: total environment steps (or per-round for iterated)")
    p.add_argument("--rollout", type=int, default=256,
                   help="PPO: rollout size before each update")
    p.add_argument("--rounds", type=int, default=3,
                   help="iterated mode: number of freeze-and-train rounds")
    p.add_argument("--eval-games", type=int, default=200,
                   help="Games per evaluation matchup")
    p.add_argument("--models-dir", type=Path, default=Path("models"),
                   help="Directory for saved model checkpoints")
    p.add_argument("--eval-only", action="store_true",
                   help="Skip training; just evaluate saved models")
    p.add_argument("--cop-model", type=Path,
                   help="Frozen cop checkpoint for --mode cross/iterated (default: models/cop_ppo_best.pt)")  # noqa: E501
    p.add_argument("--thief-model", type=Path,
                   help="Frozen thief checkpoint (default: models/thief_ppo_best.pt)")
    p.add_argument("--grid-size", type=int, default=7)
    p.add_argument("--max-steps", type=int, default=35)
    p.add_argument("--net-type", choices=["mlp", "cnn"], default="mlp",
                   help="Network backbone: mlp=fast (CPU), cnn=better for large boards")
    p.add_argument("--hidden", type=int, default=128,
                   help="Hidden layer width (128 is plenty for 7x7)")
    p.add_argument("--shaped-rewards", action="store_true",
                   help="Add distance-delta shaping to intermediate rewards")
    p.add_argument("--random-starts", action="store_true",
                   help="Randomize cop/thief starting positions each episode")
    p.add_argument("--barriers", action="store_true",
                   help="Enable cop barrier placement during training")
    p.add_argument("--barrier-quota", type=int, default=5,
                   help="Barriers the cop may place per game (default: 5)")
    return p


def _run_league(args, config: RLGameConfig) -> None:
    """Build a pool from all available checkpoints for each role and run league training."""
    import glob as _glob

    import torch as _torch

    from agent.rl.policy import RLPolicy

    models_dir = args.models_dir
    barriers_on = config.cop_barrier_quota > 0

    def _ckpt_n_channels(path: str) -> int:
        """Detect number of input channels from a checkpoint without fully loading it."""
        ckpt = _torch.load(path, map_location="cpu", weights_only=False)
        if "n_channels" in ckpt:
            return ckpt["n_channels"]
        state = ckpt["net"]
        first_w = state[next(iter(state))]
        if first_w.ndim == 4:
            return int(first_w.shape[1])
        flat_in = first_w.shape[1]
        for ch in (4, 5):
            gs = int((flat_in / ch) ** 0.5)
            if gs * gs * ch == flat_in:
                return ch
        return 4

    def _load_pool(role: str) -> tuple[list, list[float]]:
        """Load checkpoints compatible with the current config's channel count."""
        pool, weights = [], []
        required_ch = (5 if barriers_on else 4) if role == "cop" else 4

        def _load_one(path, weight):
            try:
                ch = _ckpt_n_channels(str(path))
                if ch != required_ch:
                    logger.info(f"[league] Skipping {path} (channels={ch}, need {required_ch})")
                    return
                policy = RLPolicy._load_checkpoint(Path(path), role, max_steps=config.max_steps)
                pool.append(policy)
                weights.append(weight)
                logger.info(f"[league] Added {path} (weight={weight})")
            except Exception as e:
                logger.warning(f"[league] Skipping {path}: {e}")

        candidates = [
            (models_dir / f"{role}_ppo_league_best.pt",  3.0),
            (models_dir / f"{role}_ppo_best.pt",         2.0),
        ]
        for p, w in candidates:
            if p.exists():
                _load_one(p, w)

        for p in sorted(_glob.glob(str(models_dir / f"{role}_ppo_frozen_iter_r*_best.pt"))):
            _load_one(p, 1.0)

        if not pool:
            raise SystemExit(
                f"No compatible checkpoints (n_channels={required_ch}) for role '{role}' in {models_dir}.\n"  # noqa: E501
                f"{'Train cop with barriers first: --mode selfplay --barriers' if barriers_on and role == 'cop' else ''}"  # noqa: E501
            )
        return pool, weights

    thief_pool, thief_weights = _load_pool("thief")
    cop_pool, cop_weights = _load_pool("cop")

    logger.info(f"=== League training: COP vs {len(thief_pool)} thieves ===")
    new_cop = train_ppo_league(
        "cop", thief_pool, thief_weights, config,
        total_steps=args.steps, rollout_size=args.rollout,
        models_dir=models_dir, tag="league",
    )

    logger.info(f"=== League training: THIEF vs {len(cop_pool)} cops ===")
    new_thief = train_ppo_league(
        "thief", cop_pool, cop_weights, config,
        total_steps=args.steps, rollout_size=args.rollout,
        models_dir=models_dir, tag="league",
    )

    # Evaluate against every checkpoint in each pool.
    # Must preserve cop_barrier_quota so the env produces the right obs shape.
    eval_cfg = RLGameConfig(cop_barrier_quota=config.cop_barrier_quota)
    logger.info("=== Final evaluation: league models vs all pool members ===")
    for opp in thief_pool:
        r = evaluate(new_cop, opp, eval_cfg, args.eval_games)
        print_results(f"cop_league vs thief_pool[{getattr(opp, 'role', '?')}]", r)
    for opp in cop_pool:
        r = evaluate(opp, new_thief, eval_cfg, args.eval_games)
        print_results("cop_pool vs thief_league", r)

    # Head-to-head
    r = evaluate(new_cop, new_thief, eval_cfg, args.eval_games)
    print_results("cop_league vs thief_league", r)


def main() -> None:
    args = _build_parser().parse_args()
    config = RLGameConfig(
        grid_size=args.grid_size,
        max_steps=args.max_steps,
        use_shaped_rewards=args.shaped_rewards,
        random_starts=args.random_starts,
        cop_barrier_quota=args.barrier_quota if args.barriers else 0,
    )

    if args.eval_only:
        if not args.cop_model or not args.thief_model:
            raise SystemExit("--eval-only requires --cop-model and --thief-model")
        _eval_saved(args, config)
        return

    # --- League training mode ---
    if args.mode == "league":
        _run_league(args, config)
        return

    # --- Iterated cross-training mode ---
    if args.mode == "iterated":
        train_iterated(
            config=config,
            rounds=args.rounds,
            steps_per_round=args.steps,
            rollout_size=args.rollout,
            models_dir=args.models_dir,
            net_type=args.net_type,
            hidden=args.hidden,
            eval_games=args.eval_games,
            cop_checkpoint=args.cop_model,
            thief_checkpoint=args.thief_model,
        )
        return

    # --- Cross-training mode ---
    if args.mode == "cross":
        train_cross(
            config=config,
            total_steps=args.steps,
            rollout_size=args.rollout,
            models_dir=args.models_dir,
            net_type=args.net_type,
            hidden=args.hidden,
            cop_checkpoint=args.cop_model,
            thief_checkpoint=args.thief_model,
            eval_games=args.eval_games,
        )
        return

    # --- Self-play mode ---
    dqn_cop = dqn_thief = ppo_cop = ppo_thief = None

    if args.algo in ("dqn", "both"):
        logger.info(f"=== Training DQN for {args.episodes} episodes ({args.net_type.upper()}) ===")
        dqn_cop, dqn_thief, _ = train_dqn(
            config, args.episodes, models_dir=args.models_dir,
            net_type=args.net_type, hidden=args.hidden,
        )
        r = evaluate(dqn_cop, dqn_thief, config, args.eval_games)
        print_results("DQN self-play evaluation", r)

    if args.algo in ("ppo", "both"):
        logger.info(f"=== Training PPO for {args.steps} steps ({args.net_type.upper()}) ===")
        ppo_cop, ppo_thief, _ = train_ppo(
            config, args.steps, args.rollout, models_dir=args.models_dir,
            net_type=args.net_type, hidden=args.hidden,
        )
        r = evaluate(ppo_cop, ppo_thief, config, args.eval_games)
        print_results("PPO self-play evaluation", r)

    if args.algo == "both" and all(x is not None for x in [dqn_cop, dqn_thief, ppo_cop, ppo_thief]):
        logger.info("=== Cross-algorithm comparison ===")
        compare(dqn_cop, dqn_thief, ppo_cop, ppo_thief, config, args.eval_games)


def _eval_saved(args: argparse.Namespace, config: RLGameConfig) -> None:
    """Load saved models and evaluate without training."""
    import torch
    torch.load(args.cop_model, weights_only=False)
    algo = "ppo" if args.algo == "ppo" else "dqn"

    if algo == "dqn":
        cop = DQNAgent("cop", grid_size=config.grid_size)
        thief = DQNAgent("thief", grid_size=config.grid_size)
    else:
        cop = PPOAgent("cop", grid_size=config.grid_size)
        thief = PPOAgent("thief", grid_size=config.grid_size)

    cop.load(args.cop_model)
    thief.load(args.thief_model)
    r = evaluate(cop, thief, config, args.eval_games)
    print_results(f"Loaded {algo.upper()} models", r)


if __name__ == "__main__":
    main()
