"""CLI entry point for RL training: argument parsing, league runner, main()."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from agent.rl.config import RLGameConfig
from agent.rl.dqn import DQNAgent
from agent.rl.evaluate import compare, evaluate, print_results
from agent.rl.ppo import PPOAgent
from agent.rl.train_advanced import train_ppo_league
from agent.rl.train_multi import train_cross, train_iterated
from agent.rl.train_selfplay import train_dqn, train_ppo

logger = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Train / evaluate cop-and-thief RL agents")
    p.add_argument("--algo", choices=["dqn", "ppo", "both"], default="ppo")
    p.add_argument("--mode", choices=["selfplay", "cross", "iterated", "league"], default="selfplay")
    p.add_argument("--episodes", type=int, default=30_000)
    p.add_argument("--steps", type=int, default=500_000)
    p.add_argument("--rollout", type=int, default=256)
    p.add_argument("--rounds", type=int, default=3)
    p.add_argument("--eval-games", type=int, default=200)
    p.add_argument("--models-dir", type=Path, default=Path("models"))
    p.add_argument("--eval-only", action="store_true")
    p.add_argument("--cop-model", type=Path)
    p.add_argument("--thief-model", type=Path)
    p.add_argument("--grid-size", type=int, default=7)
    p.add_argument("--max-steps", type=int, default=35)
    p.add_argument("--net-type", choices=["mlp", "cnn"], default="mlp")
    p.add_argument("--hidden", type=int, default=128)
    p.add_argument("--shaped-rewards", action="store_true")
    p.add_argument("--random-starts", action="store_true")
    p.add_argument("--barriers", action="store_true")
    p.add_argument("--barrier-quota", type=int, default=5)
    return p


def _eval_saved(args: argparse.Namespace, config: RLGameConfig) -> None:
    algo = "ppo" if args.algo == "ppo" else "dqn"
    if algo == "dqn":
        cop = DQNAgent("cop", grid_size=config.grid_size)
        thief = DQNAgent("thief", grid_size=config.grid_size)
    else:
        cop = PPOAgent("cop", grid_size=config.grid_size)
        thief = PPOAgent("thief", grid_size=config.grid_size)
    cop.load(args.cop_model); thief.load(args.thief_model)
    r = evaluate(cop, thief, config, args.eval_games)
    print_results(f"Loaded {algo.upper()} models", r)


def _run_league(args: argparse.Namespace, config: RLGameConfig) -> None:
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
        return next((ch for ch in (4, 5) if int((flat_in / ch) ** 0.5) ** 2 * ch == flat_in), 4)

    def _load_pool(role: str) -> tuple[list, list[float]]:
        pool: list = []; weights: list[float] = []
        required_ch = (5 if barriers_on else 4) if role == "cop" else 4

        def _try(path, weight):
            try:
                ch = _ckpt_n_channels(str(path))
                if ch != required_ch:
                    return
                pool.append(RLPolicy._load_checkpoint(Path(path), role, max_steps=config.max_steps))
                weights.append(weight)
                logger.info(f"[league] Added {path}")
            except Exception as e:
                logger.warning(f"[league] Skipping {path}: {e}")

        for p, w in [(models_dir / f"{role}_ppo_league_best.pt", 3.0),
                     (models_dir / f"{role}_ppo_best.pt", 2.0)]:
            if p.exists():
                _try(p, w)
        for p in sorted(_glob.glob(str(models_dir / f"{role}_ppo_frozen_iter_r*_best.pt"))):
            _try(p, 1.0)
        if not pool: raise SystemExit(f"No compatible checkpoints for '{role}' in {models_dir}")
        return pool, weights

    thief_pool, thief_weights = _load_pool("thief")
    cop_pool, cop_weights = _load_pool("cop")
    new_cop = train_ppo_league("cop", thief_pool, thief_weights, config,
                               total_steps=args.steps, rollout_size=args.rollout,
                               models_dir=models_dir, tag="league")
    new_thief = train_ppo_league("thief", cop_pool, cop_weights, config,
                                 total_steps=args.steps, rollout_size=args.rollout,
                                 models_dir=models_dir, tag="league")
    eval_cfg = RLGameConfig(cop_barrier_quota=config.cop_barrier_quota)
    r = evaluate(new_cop, new_thief, eval_cfg, args.eval_games)
    print_results("cop_league vs thief_league", r)


def main() -> None:
    args = _build_parser().parse_args()
    config = RLGameConfig(
        grid_size=args.grid_size, max_steps=args.max_steps,
        use_shaped_rewards=args.shaped_rewards, random_starts=args.random_starts,
        cop_barrier_quota=args.barrier_quota if args.barriers else 0,
    )
    if args.eval_only:
        if not args.cop_model or not args.thief_model:
            raise SystemExit("--eval-only requires --cop-model and --thief-model")
        _eval_saved(args, config); return

    if args.mode == "league":
        _run_league(args, config); return
    if args.mode == "iterated":
        train_iterated(config=config, rounds=args.rounds, steps_per_round=args.steps,
                       rollout_size=args.rollout, models_dir=args.models_dir,
                       net_type=args.net_type, hidden=args.hidden, eval_games=args.eval_games,
                       cop_checkpoint=args.cop_model, thief_checkpoint=args.thief_model); return
    if args.mode == "cross":
        train_cross(config=config, total_steps=args.steps, rollout_size=args.rollout,
                    models_dir=args.models_dir, net_type=args.net_type, hidden=args.hidden,
                    cop_checkpoint=args.cop_model, thief_checkpoint=args.thief_model,
                    eval_games=args.eval_games); return

    dqn_cop = dqn_thief = ppo_cop = ppo_thief = None
    if args.algo in ("dqn", "both"):
        dqn_cop, dqn_thief, _ = train_dqn(config, args.episodes, models_dir=args.models_dir, net_type=args.net_type, hidden=args.hidden)
        print_results("DQN self-play", evaluate(dqn_cop, dqn_thief, config, args.eval_games))
    if args.algo in ("ppo", "both"):
        ppo_cop, ppo_thief, _ = train_ppo(config, args.steps, args.rollout, models_dir=args.models_dir, net_type=args.net_type, hidden=args.hidden)
        print_results("PPO self-play", evaluate(ppo_cop, ppo_thief, config, args.eval_games))
    if args.algo == "both" and all(x is not None for x in [dqn_cop, dqn_thief, ppo_cop, ppo_thief]): compare(dqn_cop, dqn_thief, ppo_cop, ppo_thief, config, args.eval_games)


if __name__ == "__main__":
    main()
