"""Argument parser for the distillation CLI."""

from __future__ import annotations

import argparse
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=("cop", "thief"), required=True)
    parser.add_argument(
        "--teacher",
        choices=("anti_loop", "search_hybrid", "population_oracle", "ddqn"),
        required=True,
    )
    parser.add_argument("--teacher-artifact", type=Path)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--incumbent-opponent", type=Path, required=True)
    parser.add_argument("--episodes", type=int, default=1_000)
    parser.add_argument("--updates", type=int, default=300)
    parser.add_argument("--learning-rate", type=float, default=3e-4)
    parser.add_argument("--random-start-fraction", type=float, default=0.2)
    parser.add_argument("--preserve-random-base", action="store_true")
    parser.add_argument("--seed", type=int, default=20260809)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--metrics", type=Path, required=True)
    return parser
