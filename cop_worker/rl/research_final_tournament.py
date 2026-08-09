"""CLI for large held-out tournaments across research policy schemas."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cop_worker.rl.research_evaluation import (
    LegacyResearchPolicy,
    RecurrentResearchPolicy,
    ResearchPolicy,
    ScriptedResearchPolicy,
    evaluate_families,
    load_recurrent_network,
)
from cop_worker.rl.research_value_training import load_dqn_policy


def load_policy(specification: str, role: str) -> ResearchPolicy:
    """Load ``recurrent:path``, ``ddqn:path``, ``legacy:path``, or scripted family."""
    kind, value = specification.split(":", 1)
    if kind == "recurrent":
        return RecurrentResearchPolicy(
            load_recurrent_network(value, role),
            role,
            temperature=0.5 if role == "thief" else None,
        )
    if kind == "ddqn":
        return load_dqn_policy(value, role)
    if kind == "legacy":
        return LegacyResearchPolicy(value, role)
    if kind == "scripted":
        return ScriptedResearchPolicy(role, value)
    raise ValueError(f"unsupported policy specification {specification!r}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=("cop", "thief"), required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--historical-opponent", required=True)
    parser.add_argument("--series-per-family", type=int, default=20)
    parser.add_argument("--seed", type=int, default=20320009)
    parser.add_argument("--random-start", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    opponent_role = "thief" if args.role == "cop" else "cop"
    result = evaluate_families(
        load_policy(args.candidate, args.role),
        args.role,
        load_policy(args.historical_opponent, opponent_role),
        args.series_per_family,
        args.seed,
        args.random_start,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
