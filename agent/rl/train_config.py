"""CLI argument parser and league-mode orchestration for RL training."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from agent.rl.config import RLGameConfig
from agent.rl.evaluate import evaluate, print_results
from agent.rl.league import train_ppo_league

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Return the ArgumentParser for the training CLI."""
    p = argparse.ArgumentParser(description="Train / evaluate cop-and-thief RL agents")
    p.add_argument(
        "--algo", choices=["dqn", "ppo", "both"], default="ppo", help="Algorithm(s) to train"
    )
    p.add_argument(
        "--mode",
        choices=["selfplay", "cross", "iterated", "league"],
        default="selfplay",
        help="selfplay | cross | iterated | league (train vs pool of checkpoints)",
    )
    p.add_argument("--episodes", type=int, default=30_000, help="DQN: number of training episodes")
    p.add_argument(
        "--steps",
        type=int,
        default=500_000,
        help="PPO: total environment steps (or per-round for iterated)",
    )
    p.add_argument("--rollout", type=int, default=256, help="PPO: rollout size before each update")
    p.add_argument(
        "--rounds", type=int, default=3, help="iterated mode: number of freeze-and-train rounds"
    )
    p.add_argument("--eval-games", type=int, default=200, help="Games per evaluation matchup")
    p.add_argument(
        "--models-dir",
        type=Path,
        default=Path("models"),
        help="Directory for saved model checkpoints",
    )
    p.add_argument(
        "--eval-only", action="store_true", help="Skip training; just evaluate saved models"
    )
    p.add_argument(
        "--cop-model",
        type=Path,
        help="Frozen cop checkpoint for --mode cross/iterated (default: models/cop_ppo_best.pt)",
    )  # noqa: E501
    p.add_argument(
        "--thief-model",
        type=Path,
        help="Frozen thief checkpoint (default: models/thief_ppo_best.pt)",
    )
    p.add_argument("--grid-size", type=int, default=7)
    p.add_argument("--max-steps", type=int, default=35)
    p.add_argument(
        "--net-type",
        choices=["mlp", "cnn"],
        default="mlp",
        help="Network backbone: mlp=fast (CPU), cnn=better for large boards",
    )
    p.add_argument(
        "--hidden", type=int, default=128, help="Hidden layer width (128 is plenty for 7x7)"
    )
    p.add_argument(
        "--shaped-rewards",
        action="store_true",
        help="Add distance-delta shaping to intermediate rewards",
    )
    p.add_argument(
        "--random-starts",
        action="store_true",
        help="Randomize cop/thief starting positions each episode",
    )
    p.add_argument(
        "--barriers", action="store_true", help="Enable cop barrier placement during training"
    )
    p.add_argument(
        "--barrier-quota",
        type=int,
        default=5,
        help="Barriers the cop may place per game (default: 5)",
    )
    return p


def run_league(args: argparse.Namespace, config: RLGameConfig) -> None:
    """Build a pool from all available checkpoints and run league training."""
    import glob as _glob

    import torch as _torch

    from agent.rl.policy import RLPolicy

    models_dir = args.models_dir
    barriers_on = config.cop_barrier_quota > 0

    def _ckpt_n_channels(path: str) -> int:
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

        for p, w in [
            (models_dir / f"{role}_ppo_league_best.pt", 3.0),
            (models_dir / f"{role}_ppo_best.pt", 2.0),
        ]:
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
        "cop",
        thief_pool,
        thief_weights,
        config,
        total_steps=args.steps,
        rollout_size=args.rollout,
        models_dir=models_dir,
        tag="league",
    )
    logger.info(f"=== League training: THIEF vs {len(cop_pool)} cops ===")
    new_thief = train_ppo_league(
        "thief",
        cop_pool,
        cop_weights,
        config,
        total_steps=args.steps,
        rollout_size=args.rollout,
        models_dir=models_dir,
        tag="league",
    )

    eval_cfg = RLGameConfig(cop_barrier_quota=config.cop_barrier_quota)
    logger.info("=== Final evaluation: league models vs all pool members ===")
    for opp in thief_pool:
        r = evaluate(new_cop, opp, eval_cfg, args.eval_games)
        print_results(f"cop_league vs thief_pool[{getattr(opp, 'role', '?')}]", r)
    for opp in cop_pool:
        r = evaluate(opp, new_thief, eval_cfg, args.eval_games)
        print_results("cop_pool vs thief_league", r)
    r = evaluate(new_cop, new_thief, eval_cfg, args.eval_games)
    print_results("cop_league vs thief_league", r)
