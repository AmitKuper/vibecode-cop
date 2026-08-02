"""Cross-training and iterated cross-training helpers for RL agents."""

from __future__ import annotations

import logging
from pathlib import Path

from agent.rl.config import RLGameConfig
from agent.rl.evaluate import evaluate, print_results
from agent.rl.league import train_ppo_vs_frozen

logger = logging.getLogger(__name__)


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
    """Cross-train cop vs frozen best-thief AND thief vs frozen best-cop."""
    from agent.rl.policy import RLPolicy

    cfg = config or RLGameConfig()
    models_dir = Path(models_dir)
    cop_path = cop_checkpoint or models_dir / "cop_ppo_best.pt"
    thief_path = thief_checkpoint or models_dir / "thief_ppo_best.pt"

    frozen_cop = RLPolicy._load_checkpoint(Path(cop_path), "cop", max_steps=cfg.max_steps)
    frozen_thief = RLPolicy._load_checkpoint(Path(thief_path), "thief", max_steps=cfg.max_steps)
    logger.info(f"[cross] Loaded frozen cop from {cop_path}")
    logger.info(f"[cross] Loaded frozen thief from {thief_path}")

    logger.info("=== Cross-training: COP vs frozen best THIEF ===")
    new_cop = train_ppo_vs_frozen(
        "cop",
        frozen_thief,
        cfg,
        total_steps,
        rollout_size,
        models_dir=models_dir,
        net_type=net_type,
        hidden=hidden,
        tag="v2",
    )
    logger.info("=== Cross-training: THIEF vs frozen best COP ===")
    new_thief = train_ppo_vs_frozen(
        "thief",
        frozen_cop,
        cfg,
        total_steps,
        rollout_size,
        models_dir=models_dir,
        net_type=net_type,
        hidden=hidden,
        tag="v2",
    )

    logger.info("=== Evaluating cross-trained models ===")
    from agent.rl.eval_compare import compare

    r = evaluate(new_cop, new_thief, cfg, eval_games)
    print_results("Cross-trained cop vs cross-trained thief", r)
    logger.info("=== Comparing cross-trained vs original PPO ===")
    compare(frozen_cop, frozen_thief, new_cop, new_thief, cfg, eval_games)
    return new_cop, new_thief


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
    """Iterated cross-training: alternate freezing best cop/thief for N rounds."""
    from agent.rl.policy import RLPolicy

    cfg = config or RLGameConfig(use_shaped_rewards=True, random_starts=True)
    models_dir = Path(models_dir)
    models_dir.mkdir(parents=True, exist_ok=True)

    cop_path = cop_checkpoint or models_dir / "cop_ppo_best.pt"
    thief_path = thief_checkpoint or models_dir / "thief_ppo_best.pt"
    frozen_cop = RLPolicy._load_checkpoint(Path(cop_path), "cop", max_steps=cfg.max_steps)
    frozen_thief = RLPolicy._load_checkpoint(Path(thief_path), "thief", max_steps=cfg.max_steps)
    logger.info(f"[iterated] Bootstrapping from {cop_path} and {thief_path}")

    for rnd in range(1, rounds + 1):
        logger.info(f"\n{'=' * 60}\n  ITERATED ROUND {rnd}/{rounds}\n{'=' * 60}")
        tag = f"iter_r{rnd}"
        logger.info(f"[round {rnd}] Training COP vs frozen thief ...")
        new_cop = train_ppo_vs_frozen(
            "cop",
            frozen_thief,
            cfg,
            steps_per_round,
            rollout_size,
            models_dir=models_dir,
            net_type=net_type,
            hidden=hidden,
            tag=tag,
        )
        logger.info(f"[round {rnd}] Training THIEF vs new frozen cop ...")
        new_thief = train_ppo_vs_frozen(
            "thief",
            new_cop,
            cfg,
            steps_per_round,
            rollout_size,
            models_dir=models_dir,
            net_type=net_type,
            hidden=hidden,
            tag=tag,
        )
        eval_cfg = RLGameConfig()
        r = evaluate(new_cop, new_thief, eval_cfg, eval_games)
        print_results(f"Round {rnd} evaluation (cop_iter vs thief_iter)", r)
        frozen_cop, frozen_thief = new_cop, new_thief

    logger.info("[iterated] All rounds complete.")
    return frozen_cop, frozen_thief
