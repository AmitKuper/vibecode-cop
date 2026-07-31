"""RL training public API — re-exports from focused sub-modules.

Modules:
  train_selfplay  — train_dqn, train_ppo (self-play loops)
  train_advanced  — train_ppo_vs_frozen, train_ppo_league
  train_multi     — train_cross, train_iterated
  train_cli       — _build_parser, main (CLI entry point)

CLI:
  python -m agent.rl.train --algo ppo --steps 500000
"""

from agent.rl.train_advanced import train_ppo_league, train_ppo_vs_frozen
from agent.rl.train_cli import main
from agent.rl.train_multi import train_cross, train_iterated
from agent.rl.train_selfplay import train_dqn, train_ppo

__all__ = [
    "train_dqn",
    "train_ppo",
    "train_ppo_vs_frozen",
    "train_ppo_league",
    "train_cross",
    "train_iterated",
    "main",
]

if __name__ == "__main__":
    main()
