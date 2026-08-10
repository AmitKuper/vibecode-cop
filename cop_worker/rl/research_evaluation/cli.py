"""CLI entry: run the research tournaments and write evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cop_worker.rl.recurrent_policy import file_sha256
from cop_worker.rl.research_evaluation.policies_recurrent import (
    RecurrentResearchPolicy,
    load_recurrent_network,
)
from cop_worker.rl.research_evaluation.tournaments import evaluate_crossplay


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cop", type=Path, required=True)
    parser.add_argument("--thief", type=Path, required=True)
    parser.add_argument("--series", type=int, default=20)
    parser.add_argument("--seed", type=int, default=20260809)
    parser.add_argument("--random-start", action="store_true")
    parser.add_argument("--cop-search-strength", type=float, default=0.0)
    parser.add_argument("--thief-search-strength", type=float, default=0.0)
    parser.add_argument("--search-depth", type=int, choices=(1, 2), default=1)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    cop = RecurrentResearchPolicy(
        load_recurrent_network(args.cop, "cop"),
        "cop",
        search_strength=args.cop_search_strength,
        search_depth=args.search_depth,
    )
    thief = RecurrentResearchPolicy(
        load_recurrent_network(args.thief, "thief"),
        "thief",
        temperature=0.5,
        search_strength=args.thief_search_strength,
        search_depth=args.search_depth,
    )
    result = {
        "seed": args.seed,
        "cop_artifact": str(args.cop),
        "cop_sha256": file_sha256(args.cop),
        "thief_artifact": str(args.thief),
        "thief_sha256": file_sha256(args.thief),
        "crossplay": evaluate_crossplay(cop, thief, args.series, args.seed, args.random_start),
    }
    rendered = json.dumps(result, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    print(rendered)
