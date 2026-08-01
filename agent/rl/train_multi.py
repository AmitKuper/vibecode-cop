"""Multi-round training: cross-training and iterated self-play."""

from __future__ import annotations

import logging
from pathlib import Path

from agent.rl.config import RLGameConfig
from agent.rl.evaluate import compare, evaluate, print_results
from agent.rl.train_advanced import train_ppo_vs_frozen

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
    cfg = config or RLGameConfig()
    models_dir = Path(models_dir)
    cop_path   = cop_checkpoint   or models_dir / "cop_ppo_best.pt"
    thief_path = thief_checkpoint or models_dir / "thief_ppo_best.pt"

    from agent.rl.policy import RLPolicy
    frozen_cop   = RLPolicy._load_checkpoint(Path(cop_path),   "cop",   max_steps=cfg.max_steps)
    frozen_thief = RLPolicy._load_checkpoint(Path(thief_path), "thief", max_steps=cfg.max_steps)
    logger.info(f"[cross] Frozen cop={cop_path}, thief={thief_path}")

    logger.info("=== Cross-training: COP vs frozen best THIEF ===")
    new_cop = train_ppo_vs_frozen(
        "cop", frozen_thief, cfg, total_steps, rollout_size,
        models_dir=models_dir, net_type=net_type, hidden=hidden, tag="v2",
    )
    logger.info("=== Cross-training: THIEF vs frozen best COP ===")
    new_thief = train_ppo_vs_frozen(
        "thief", frozen_cop, cfg, total_steps, rollout_size,
        models_dir=models_dir, net_type=net_type, hidden=hidden, tag="v2",
    )

    r = evaluate(new_cop, new_thief, cfg, eval_games)
    print_results("Cross-trained cop vs cross-trained thief", r)
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
    cfg = config or RLGameConfig(use_shaped_rewards=True, random_starts=True)
    models_dir = Path(models_dir)
    models_dir.mkdir(parents=True, exist_ok=True)

    cop_path   = cop_checkpoint   or models_dir / "cop_ppo_best.pt"
    thief_path = thief_checkpoint or models_dir / "thief_ppo_best.pt"

    from agent.rl.policy import RLPolicy
    frozen_cop   = RLPolicy._load_checkpoint(Path(cop_path),   "cop",   max_steps=cfg.max_steps)
    frozen_thief = RLPolicy._load_checkpoint(Path(thief_path), "thief", max_steps=cfg.max_steps)
    logger.info(f"[iterated] Bootstrapping from {cop_path} and {thief_path}")

    for rnd in range(1, rounds + 1):
        logger.info(f"\n{'='*60}\n  ITERATED ROUND {rnd}/{rounds}\n{'='*60}")
        tag = f"iter_r{rnd}"
        logger.info(f"[round {rnd}] Training COP vs frozen thief ...")
        frozen_cop = train_ppo_vs_frozen(
            "cop", frozen_thief, cfg, steps_per_round, rollout_size,
            models_dir=models_dir, net_type=net_type, hidden=hidden, tag=tag,
        )
        logger.info(f"[round {rnd}] Training THIEF vs new frozen cop ...")
        frozen_thief = train_ppo_vs_frozen(
            "thief", frozen_cop, cfg, steps_per_round, rollout_size,
            models_dir=models_dir, net_type=net_type, hidden=hidden, tag=tag,
        )
        r = evaluate(frozen_cop, frozen_thief, cfg, eval_games)
        print_results(f"Round {rnd} evaluation", r)

    logger.info("[iterated] All rounds complete.")
    return frozen_cop, frozen_thief
